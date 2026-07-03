"""Daily Briefing API routes."""

import json
import logging
import asyncio
import base64
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.database import get_db, async_session
from app.models import DailyBriefing, Setting
from app.schemas import DailyBriefingOut, DailyBriefingGenerate
from app.config import AUDIO_DIR
from app.services.briefing_generator import generate_briefing as gen_briefing
from app.services.tts_service import generate_briefing_audio

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/daily-briefings", tags=["Daily Briefings"])

# ─── Background generation tracking ───
# Ensures at most one audio generation per briefing, even if the client disconnects.
# Structure: {briefing_id: {"queue": asyncio.Queue, "task": asyncio.Task, ...}}
_active_generations: dict[int, dict] = {}
_active_generations_lock = asyncio.Lock()


async def _start_generation(
    briefing_id: int,
    backend,
    text: str,
    ref_audio_id: str | None,
) -> asyncio.Queue | None:
    """Start (or attach to) a background audio generation task for a briefing.

    Returns the asyncio.Queue that the SSE endpoint reads from, or
    ``None`` if a generation is already in progress and its queue is
    returned.

    The background task:
      - writes audio chunks directly to a ``.tmp.wav`` file
      - puts each chunk's SSE payload into the queue for streaming
      - on completion renames ``.tmp.wav`` → ``.wav`` and updates the DB
      - on client disconnect *the background task continues* — the SSE
        generator exits but the :func:`_run_generation` coroutine lives on.
    """
    async with _active_generations_lock:
        existing = _active_generations.get(briefing_id)
        if existing is not None:
            # Generation already running — return its queue for re-attachment
            return existing["queue"]

        queue: asyncio.Queue = asyncio.Queue()
        info = {"queue": queue, "temp_path": None, "final_path": None, "task": None}
        _active_generations[briefing_id] = info

    # Start the actual work *outside* the lock
    task = asyncio.create_task(
        _run_generation(briefing_id, backend, text, ref_audio_id, queue),
    )
    async with _active_generations_lock:
        _active_generations[briefing_id]["task"] = task

    return queue


async def _stop_generation(briefing_id: int):
    """Cancel a running generation, if any, and wait for cleanup."""
    async with _active_generations_lock:
        info = _active_generations.pop(briefing_id, None)
    if info and info["task"] and not info["task"].done():
        info["task"].cancel()
        try:
            await info["task"]
        except asyncio.CancelledError:
            pass


async def _run_generation(
    briefing_id: int,
    backend,
    text: str,
    ref_audio_id: str | None,
    queue: asyncio.Queue,
):
    """Background coroutine — generate audio, write to temp file, update DB.

    This is deliberately kept *outside* the SSE generator so it outlives
    a client disconnect.  The SSE generator is just a consumer of *queue*.
    """
    import numpy as np
    import soundfile as sf

    temp_path: Path | None = None
    final_path: Path | None = None
    success = False

    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_path = AUDIO_DIR / f"briefing_{briefing_id}_{timestamp}_tmp.wav"
        final_path = AUDIO_DIR / f"briefing_{briefing_id}_{timestamp}.wav"

        # Persist temp/final paths for potential cleanup
        async with _active_generations_lock:
            info = _active_generations.get(briefing_id)
            if info:
                info["temp_path"] = temp_path
                info["final_path"] = final_path

        # Mark as generating
        async with async_session() as bg_db:
            b = await bg_db.get(DailyBriefing, briefing_id)
            if b:
                b.status = "generating"
                await bg_db.commit()

        if backend.name == "moss-tts-nano":
            # ── Streaming (nano) ──
            first = True
            sf_file: sf.SoundFile | None = None
            total = 0

            # Use a fresh DB session (the endpoint's session may be closed
            # by the time this background task runs)
            async with async_session() as gen_db:
                async for audio_bytes, sr, idx, total in backend.generate_audio_streaming(
                    text=text, db=gen_db, ref_audio_id=ref_audio_id,
                ):
                    audio_np = np.frombuffer(audio_bytes, dtype=np.float32)

                    if first:
                        channels = audio_np.shape[1] if audio_np.ndim == 2 else 1
                        sf_file = sf.SoundFile(
                            str(temp_path), mode="w",
                            samplerate=int(sr), channels=int(channels),
                            subtype="PCM_16",
                        )
                        first = False

                    # Write to temp file (no in-memory accumulation ✓)
                    write_arr = audio_np.reshape(-1, 1) if audio_np.ndim == 1 else audio_np
                    sf_file.write(write_arr)

                    # Put chunk in queue for SSE consumers
                    await queue.put({
                        "type": "chunk",
                        "index": idx,
                        "total": total,
                        "sample_rate": int(sr),
                        "audio_base64": base64.b64encode(audio_bytes).decode("utf-8"),
                    })

            if sf_file:
                sf_file.close()

            # Rename tmp → final
            if temp_path.exists():
                temp_path.rename(final_path)
            audio_path = str(final_path.relative_to(AUDIO_DIR))

            async with async_session() as bg_db:
                b = await bg_db.get(DailyBriefing, briefing_id)
                if b:
                    b.audio_path = audio_path
                    b.status = "completed"
                    await bg_db.commit()

            await queue.put({"type": "done", "audio_path": audio_path})
            logger.info("Background generation complete: %s", final_path)
            success = True

        else:
            # ── Non-streaming (moss-ttsd) ──
            ok = await backend.generate_audio(
                text=text, output_path=temp_path,
                ref_audio_id=ref_audio_id,
            )
            if ok and temp_path.exists():
                temp_path.rename(final_path)
                audio_path = str(final_path.relative_to(AUDIO_DIR))

                async with async_session() as bg_db:
                    b = await bg_db.get(DailyBriefing, briefing_id)
                    if b:
                        b.audio_path = audio_path
                        b.status = "completed"
                        await bg_db.commit()

                # Read full audio and push as single chunk
                audio_data, sr = sf.read(str(final_path))
                audio_bytes = audio_data.astype(np.float32).tobytes()
                await queue.put({
                    "type": "chunk",
                    "index": 0, "total": 1,
                    "sample_rate": int(sr),
                    "audio_base64": base64.b64encode(audio_bytes).decode("utf-8"),
                })
                await queue.put({"type": "done", "audio_path": audio_path})
                logger.info("Background generation complete (non-streaming): %s", final_path)
                success = True
            else:
                await queue.put({"type": "error", "message": "Audio generation failed"})

    except asyncio.CancelledError:
        # Generation cancelled (via _stop_generation) — clean up
        logger.info("Background generation cancelled for briefing %s", briefing_id)
        await queue.put({"type": "error", "message": "生成已取消"})
        async with async_session() as bg_db:
            b = await bg_db.get(DailyBriefing, briefing_id)
            if b and b.status == "generating":
                b.status = "failed"
                await bg_db.commit()

    except Exception as e:
        logger.error("Background generation failed for briefing %s: %s", briefing_id, e)
        await queue.put({"type": "error", "message": str(e)})
        async with async_session() as bg_db:
            b = await bg_db.get(DailyBriefing, briefing_id)
            if b and b.status == "generating":
                b.status = "failed"
                await bg_db.commit()

    finally:
        # Clean up temp file if still around
        if temp_path and temp_path.exists():
            temp_path.unlink(missing_ok=True)
        # Remove from active tracking
        async with _active_generations_lock:
            _active_generations.pop(briefing_id, None)


@router.post("/generate", response_model=DailyBriefingOut, status_code=201)
async def create_briefing(
    data: DailyBriefingGenerate = None,
    db: AsyncSession = Depends(get_db),
):
    """Generate a new daily briefing with optional time range and group filter."""
    if data is None:
        from app.schemas import DailyBriefingGenerate
        data = DailyBriefingGenerate()

    # Read TTS engine setting to determine script style
    result = await db.execute(select(Setting).where(Setting.key == "tts_engine"))
    tts_setting = result.scalar_one_or_none()
    tts_engine = tts_setting.value if tts_setting else "moss-ttsd"

    briefing = await gen_briefing(
        db,
        date_str=data.date,
        time_range=data.time_range,
        group_id=data.group_id,
        tts_engine=tts_engine,
        ref_audio_id=data.ref_audio_id,
    )

    if briefing is None:
        return {"no_content": True, "message": "所选时间范围内没有新文章，无需生成日报。"}

    # Note: TTS is triggered on-demand via stream-audio endpoint.
    # When user visits the detail page, streaming starts immediately.
    return briefing


@router.get("", response_model=list[DailyBriefingOut])
async def list_briefings(db: AsyncSession = Depends(get_db)):
    """List all daily briefings."""
    result = await db.execute(
        select(DailyBriefing).order_by(desc(DailyBriefing.date))
    )
    return result.scalars().all()


@router.get("/tts-backends")
async def list_tts_backends(db: AsyncSession = Depends(get_db)):
    """Get available TTS backends and their status."""
    from app.services.tts_service import get_available_backends, get_active_backend
    backends = await get_available_backends(db)
    active = await get_active_backend(db)
    return {
        "backends": {k: {"available": v} for k, v in backends.items()},
        "active": active.name,
    }


@router.get("/{briefing_id}", response_model=DailyBriefingOut)
async def get_briefing(briefing_id: int, db: AsyncSession = Depends(get_db)):
    """Get a daily briefing."""
    briefing = await db.get(DailyBriefing, briefing_id)
    if not briefing:
        raise HTTPException(status_code=404, detail="Briefing not found")
    return briefing


@router.delete("/{briefing_id}")
async def delete_briefing(briefing_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a daily briefing."""
    briefing = await db.get(DailyBriefing, briefing_id)
    if not briefing:
        raise HTTPException(status_code=404, detail="Briefing not found")
    await db.delete(briefing)
    await db.flush()
    return {"message": "Briefing deleted"}


@router.post("/{briefing_id}/regenerate-audio")
async def regenerate_briefing_audio(briefing_id: int, db: AsyncSession = Depends(get_db)):
    """Delete existing audio and reset status so streaming regenerates it.

    If a generation is currently running for this briefing, it will be
    cancelled first.
    """
    briefing = await db.get(DailyBriefing, briefing_id)
    if not briefing:
        raise HTTPException(status_code=404, detail="Briefing not found")

    # Cancel any running generation for this briefing
    await _stop_generation(briefing_id)

    # Delete existing audio file
    if briefing.audio_path:
        audio_file = AUDIO_DIR / briefing.audio_path
        if audio_file.exists():
            audio_file.unlink()
            logger.info(f"Deleted existing audio: {audio_file}")

    # Reset briefing record
    briefing.audio_path = None
    briefing.status = "completed"  # frontend will see no audio_path and trigger streaming
    await db.flush()

    return {"message": "Audio reset, refresh to regenerate"}


@router.get("/{briefing_id}/stream-audio")
async def stream_briefing_audio(briefing_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """Stream briefing audio via SSE — plays on frontend as chunks are generated.

    Key design decisions
    --------------------
    * Audio generation runs as a **background asyncio.Task** that writes
      chunks directly to a ``.tmp.wav`` file (no in-memory accumulation).
    * The SSE generator is **only a consumer** of an ``asyncio.Queue`` that
      the background task fills.
    * If the client disconnects, the SSE generator exits silently but the
      background task **continues** — the final ``.wav`` file is still saved
      and the DB record updated.
    * At most one generation per briefing is enforced via
      :data:`_active_generations`.
    """
    from app.services.tts_service import get_active_backend

    briefing = await db.get(DailyBriefing, briefing_id)
    if not briefing:
        raise HTTPException(status_code=404, detail="Briefing not found")
    if not briefing.script_text or briefing.script_text in ("暂无新闻更新。", ""):
        raise HTTPException(status_code=400, detail="Briefing has no content to synthesize")

    # Already has audio — tell client to use /audio endpoint
    if briefing.audio_path:
        audio_file = AUDIO_DIR / briefing.audio_path
        if audio_file.exists():
            raise HTTPException(status_code=400, detail="Audio already exists, use /audio endpoint")

    backend = await get_active_backend(db)

    # Start (or attach to) background generation
    queue = await _start_generation(
        briefing_id,
        backend,
        text=briefing.script_text,
        ref_audio_id=briefing.ref_audio_id,
    )

    async def event_generator():
        """Consume the generation queue and yield SSE events.

        Detects client disconnect via ``request.is_disconnected()`` and
        via ``GeneratorExit``.  In either case the generator exits cleanly
        while the background generation task lives on.
        """
        try:
            while True:
                try:
                    # Wait for next chunk (with timeout so we can poll
                    # for disconnect periodically)
                    data = await asyncio.wait_for(queue.get(), timeout=2.0)
                    yield f"data: {json.dumps(data)}\n\n"
                    if data.get("type") in ("done", "error"):
                        return
                except asyncio.TimeoutError:
                    # Queue empty — check if client is still there
                    if await request.is_disconnected():
                        logger.info(
                            "Client disconnected from briefing %s, "
                            "generation continues in background",
                            briefing_id,
                        )
                        return
        except GeneratorExit:
            # Client disconnected (Starlette called aclose())
            logger.info(
                "SSE connection closed for briefing %s, "
                "generation continues in background",
                briefing_id,
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{briefing_id}/audio")
async def get_briefing_audio(briefing_id: int, db: AsyncSession = Depends(get_db)):
    """Get the audio file for a briefing."""
    briefing = await db.get(DailyBriefing, briefing_id)
    if not briefing:
        raise HTTPException(status_code=404, detail="Briefing not found")
    if not briefing.audio_path:
        raise HTTPException(status_code=404, detail="No audio available")
    audio_file = AUDIO_DIR / briefing.audio_path
    if not audio_file.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")
    return FileResponse(str(audio_file), media_type="audio/wav")

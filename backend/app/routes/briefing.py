"""Daily Briefing API routes."""

import json
import logging
import asyncio
import base64
import os as stdlib_os
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.database import get_db, async_session
from app.models import DailyBriefing
from app.schemas import DailyBriefingOut, DailyBriefingGenerate
from app.config import AUDIO_DIR
from app.services.briefing_generator import generate_briefing as gen_briefing
from app.services.tts_service import get_active_backend

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/daily-briefings", tags=["Daily Briefings"])

# ─── Background generation tracking ───
_active_generations: dict[int, dict] = {}
_active_generations_lock = asyncio.Lock()


# ─── Helpers ───

async def _update_briefing_status(briefing_id: int, status: str):
    """Update a briefing's status in a fresh session."""
    async with async_session() as bg_db:
        b = await bg_db.get(DailyBriefing, briefing_id)
        if b:
            b.status = status
            await bg_db.commit()


async def _finalize_audio_file(briefing_id: int, temp_path: Path, final_path: Path) -> str | None:
    """Rename temp → final and update DB. Returns relative audio_path or None on failure."""
    if not temp_path.exists():
        logger.error("Temp file missing for briefing %s: %s", briefing_id, temp_path)
        return None

    fsize = temp_path.stat().st_size
    if fsize <= 44:  # WAV header only = empty audio
        logger.error("Temp file too small (%s bytes) for briefing %s", fsize, briefing_id)
        return None

    temp_path.rename(final_path)
    audio_path = str(final_path.relative_to(AUDIO_DIR))
    logger.info("File saved: %s (%s bytes)", final_path, fsize)

    async with async_session() as bg_db:
        b = await bg_db.get(DailyBriefing, briefing_id)
        if b:
            b.audio_path = audio_path
            b.status = "completed"
            await bg_db.commit()

    return audio_path


async def _fail_briefing(briefing_id: int, queue: asyncio.Queue, message: str):
    """Mark briefing as failed and notify SSE consumers."""
    logger.error("Briefing %s failed: %s", briefing_id, message)
    try:
        queue.put_nowait({"type": "error", "message": message})
    except Exception:
        pass
    await _update_briefing_status(briefing_id, "failed")


# ─── Generation lifecycle ───

async def _start_generation(
    briefing_id: int,
    text: str,
    ref_audio_id: str | None,
) -> tuple[asyncio.Queue, list[dict]]:
    """Start (or attach to) a background audio generation task for a briefing.

    Returns (queue, chunks) where chunks is a replayable list of already-generated chunks.
    """
    async with _active_generations_lock:
        existing = _active_generations.get(briefing_id)
        if existing is not None:
            return existing["queue"], existing["chunks"]

        queue: asyncio.Queue = asyncio.Queue()
        info = {"queue": queue, "chunks": [], "temp_path": None, "final_path": None, "task": None}
        _active_generations[briefing_id] = info

    backend = get_active_backend()
    task = asyncio.create_task(
        _run_generation(briefing_id, backend, text, ref_audio_id, queue),
    )
    async with _active_generations_lock:
        _active_generations[briefing_id]["task"] = task

    return queue, info["chunks"]


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


async def run_generation_headless(
    briefing_id: int, text: str, ref_audio_id: str | None = None,
) -> bool:
    """Start audio generation and wait for completion (no SSE client).

    Used by the task scheduler for headless audio generation.
    """
    queue, _chunks = await _start_generation(briefing_id, text, ref_audio_id)
    return await wait_for_generation(briefing_id)


async def wait_for_generation(briefing_id: int, timeout: float = 600) -> bool:
    """Wait for a briefing's audio generation to complete.

    Returns True if generation succeeded, False otherwise.
    """
    deadline = stdlib_os.times().elapsed + timeout  # approximate; use time.monotonic()
    import time as _time
    deadline = _time.monotonic() + timeout
    while _time.monotonic() < deadline:
        async with _active_generations_lock:
            info = _active_generations.get(briefing_id)
            if info is None:
                # Generation finished and cleaned up — check final status
                async with async_session() as db:
                    b = await db.get(DailyBriefing, briefing_id)
                    return b is not None and b.status == "completed"
        await asyncio.sleep(1)
    logger.warning("wait_for_generation(%s) timed out after %ss", briefing_id, timeout)
    return False


async def _run_generation(
    briefing_id: int,
    backend,
    text: str,
    ref_audio_id: str | None,
    queue: asyncio.Queue,
):
    """Background coroutine — linear flow with step tracking.

    Step-by-step:
      1. setup_paths     — create temp/final file paths
      2. mark_generating — set briefing status = "generating"
      3. open_soundfile  — open .tmp.wav for writing
      4. generation_loop — async for each chunk: sf_file.write + queue.put_nowait
      5. close_file      — flush → fsync → close
      6. save_file       — rename temp → final, update DB, queue "done"

    Uses put_nowait() on the queue — never blocks, never drops chunks.
    The queue is a best-effort SSE channel; file writing is independent.
    """
    import numpy as np
    import soundfile as sf

    temp_path: Path | None = None
    final_path: Path | None = None
    sf_file: sf.SoundFile | None = None
    actual_written = 0
    expected_total = 0
    step = "init"

    try:
        # ── Step 1: setup_paths ──
        step = "setup_paths"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_path = AUDIO_DIR / f"briefing_{briefing_id}_{timestamp}_tmp.wav"
        final_path = AUDIO_DIR / f"briefing_{briefing_id}_{timestamp}.wav"
        logger.info("[%s] temp=%s final=%s", briefing_id, temp_path.name, final_path.name)

        # ── Step 2: mark_generating ──
        step = "mark_generating"
        await _update_briefing_status(briefing_id, "generating")

        # ── Step 3: open_soundfile ──
        step = "open_soundfile"
        # First chunk will set sample rate; open lazily inside loop

        # ── Step 4: generation_loop ──
        step = "generation_loop"
        async with async_session() as gen_db:
            async for audio_bytes, sr, idx, total in backend.generate_audio_streaming(
                text=text, db=gen_db, ref_audio_id=ref_audio_id,
            ):
                if sf_file is None:
                    sf_file = sf.SoundFile(
                        str(temp_path), mode="w",
                        samplerate=int(sr), channels=1,
                        subtype="PCM_16",
                    )
                    expected_total = total

                audio_np = np.frombuffer(audio_bytes, dtype=np.float32)
                write_arr = audio_np.reshape(-1, 1) if audio_np.ndim == 1 else audio_np
                sf_file.write(write_arr)
                actual_written += 1

                # Non-blocking queue put — never blocks, never drops.
                chunk_data = {
                    "type": "chunk",
                    "index": idx,
                    "total": total,
                    "sample_rate": int(sr),
                    "audio_base64": base64.b64encode(audio_bytes).decode("utf-8"),
                }
                queue.put_nowait(chunk_data)
                # Also cache for late-joining SSE clients to replay from start
                async with _active_generations_lock:
                    gen_info = _active_generations.get(briefing_id)
                    if gen_info is not None:
                        gen_info.setdefault("chunks", []).append(chunk_data)

        logger.info(
            "[%s] generation_loop done: %d/%d chunks written",
            briefing_id, actual_written, expected_total,
        )

        # ── Step 5: close_file ──
        step = "close_file"
        if sf_file is not None:
            sf_file.flush()
            try:
                stdlib_os.fsync(sf_file.fileno())
            except (OSError, AttributeError):
                # fileno() not available in some soundfile builds
                pass
            sf_file.close()
            sf_file = None
            logger.info("[%s] soundfile closed, size=%s", briefing_id,
                        temp_path.stat().st_size if temp_path.exists() else "N/A")

        # ── Step 6: save_file ──
        step = "save_file"
        audio_path = await _finalize_audio_file(briefing_id, temp_path, final_path)
        if audio_path:
            queue.put_nowait({"type": "done", "audio_path": audio_path})
            logger.info("[%s] generation complete: %s", briefing_id, final_path)
        else:
            queue.put_nowait({"type": "error", "message": "音频文件保存失败"})
            await _update_briefing_status(briefing_id, "failed")

    except asyncio.CancelledError:
        logger.info("[%s] generation cancelled at step=%s", briefing_id, step)
        await _fail_briefing(briefing_id, queue, "生成已取消")

    except Exception as e:
        logger.error("[%s] generation failed at step=%s: %s", briefing_id, step, e, exc_info=True)
        await _fail_briefing(briefing_id, queue, str(e))

    finally:
        if sf_file is not None:
            try:
                sf_file.close()
            except Exception:
                pass
        # Clean up: only if final doesn't exist (rename didn't happen)
        if final_path and final_path.exists():
            pass  # success — keep final
        elif temp_path and temp_path.exists():
            temp_path.unlink(missing_ok=True)
        async with _active_generations_lock:
            _active_generations.pop(briefing_id, None)
            logger.info("[%s] removed from active generations", briefing_id)


@router.post("/generate", response_model=DailyBriefingOut, status_code=201)
async def create_briefing(
    data: DailyBriefingGenerate = None,
    db: AsyncSession = Depends(get_db),
):
    """Generate a new daily briefing with optional time range and group filter."""
    if data is None:
        from app.schemas import DailyBriefingGenerate
        data = DailyBriefingGenerate()

    briefing = await gen_briefing(
        db,
        date_str=data.date,
        time_range=data.time_range,
        group_id=data.group_id,
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
async def list_tts_backends():
    """Get available TTS backends and their status."""
    from app.services.tts_service import get_available_backends, get_active_backend
    backends = await get_available_backends()
    active = get_active_backend()
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

    # Start (or attach to) background generation
    queue, existing_chunks = await _start_generation(
        briefing_id,
        text=briefing.script_text,
        ref_audio_id=briefing.ref_audio_id,
    )

    async def event_generator():
        """Consume the generation queue and yield SSE events.

        First replays all cached chunks (for late-joining clients that
        missed earlier chunks), then consumes the live queue.

        Detects client disconnect via ``request.is_disconnected()`` and
        via ``GeneratorExit``.  In either case the generator exits cleanly
        while the background generation task lives on.
        """
        # Replay all already-generated chunks for this new client.
        # Take a snapshot (shallow copy) to avoid race with _run_generation
        # appending to the same list while we iterate.
        for chunk_data in list(existing_chunks):
            yield f"data: {json.dumps(chunk_data)}\n\n"

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

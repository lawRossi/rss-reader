"""Daily Briefing API routes."""

import json
import logging
import asyncio
import base64
from datetime import datetime

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

# In-memory lock to prevent concurrent audio streaming for the same briefing
_streaming_locks: dict[int, asyncio.Lock] = {}
_streaming_lock_global = asyncio.Lock()


async def _acquire_streaming_lock(briefing_id: int) -> bool:
    """Try to acquire the streaming lock for a briefing. Returns True if acquired."""
    async with _streaming_lock_global:
        if briefing_id in _streaming_locks:
            return False  # Already streaming
        _streaming_locks[briefing_id] = asyncio.Lock()
    # Acquire the per-briefing lock (will be held for the entire streaming duration)
    await _streaming_locks[briefing_id].acquire()
    return True


async def _release_streaming_lock(briefing_id: int):
    """Release the streaming lock for a briefing."""
    async with _streaming_lock_global:
        lock = _streaming_locks.pop(briefing_id, None)
        if lock and lock.locked():
            lock.release()


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
    """Delete existing audio and reset status so streaming regenerates it."""
    briefing = await db.get(DailyBriefing, briefing_id)
    if not briefing:
        raise HTTPException(status_code=404, detail="Briefing not found")

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
    """Stream briefing audio via SSE — plays on frontend as chunks are generated."""
    from app.services.tts_service import get_active_backend, MossTTSNanoBackend, MossTTSDMLXBackend

    briefing = await db.get(DailyBriefing, briefing_id)
    if not briefing:
        raise HTTPException(status_code=404, detail="Briefing not found")
    if not briefing.script_text or briefing.script_text in ("暂无新闻更新。", ""):
        raise HTTPException(status_code=400, detail="Briefing has no content to synthesize")

    # Already has audio — return immediately
    if briefing.audio_path:
        audio_file = AUDIO_DIR / briefing.audio_path
        if audio_file.exists():
            raise HTTPException(status_code=400, detail="Audio already exists, use /audio endpoint")

    backend = await get_active_backend(db)

    async def event_generator():
        """Generate SSE events with audio chunks."""
        import numpy as np

        all_audio = []
        sample_rate = None
        final_audio_path = ""

        # Acquire lock at generator start (runs when StreamingResponse starts iterating)
        lock_held = await _acquire_streaming_lock(briefing_id)
        if not lock_held:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Audio is already being generated for this briefing'})}\n\n"
            return

        # Mark as generating (under lock, preventing concurrent updates)
        async with async_session() as bg_db:
            b = await bg_db.get(DailyBriefing, briefing.id)
            if b:
                b.status = "generating"
                await bg_db.commit()

        try:
            if backend.name == "moss-tts-nano":
                # Streaming generation — yields chunks as they're ready
                async for audio_bytes, sr, idx, total in backend.generate_audio_streaming(
                    text=briefing.script_text, db=db, ref_audio_id=briefing.ref_audio_id,
                ):
                    if sample_rate is None:
                        sample_rate = sr
                    all_audio.append(np.frombuffer(audio_bytes, dtype=np.float32))

                    # Send chunk via SSE
                    chunk_data = {
                        "type": "chunk",
                        "index": idx,
                        "total": total,
                        "sample_rate": sample_rate,
                        "audio_base64": base64.b64encode(audio_bytes).decode("utf-8"),
                    }
                    yield f"data: {json.dumps(chunk_data)}\n\n"

                # No chunks generated — bail out
                if not all_audio:
                    yield f"data: {json.dumps({'type': 'error', 'message': '音频生成失败：无有效音频数据'})}\n\n"
                    return

                # Combine all chunks and save final audio file
                combined = np.concatenate(all_audio, axis=0) if len(all_audio) > 1 else all_audio[0]
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_path = AUDIO_DIR / f"briefing_{briefing.id}_{timestamp}.wav"

                def _save():
                    import soundfile as sf
                    sf.write(str(output_path), combined, sample_rate)

                await asyncio.get_running_loop().run_in_executor(None, _save)
                final_audio_path = str(output_path.relative_to(AUDIO_DIR))

                # Update briefing record
                async with async_session() as bg_db:
                    b = await bg_db.get(DailyBriefing, briefing.id)
                    if b:
                        b.audio_path = final_audio_path
                        b.status = "completed"
                        await bg_db.commit()

                logger.info(f"Streaming complete, audio saved: {output_path}")

            else:
                # Non-streaming backend (moss-ttsd): generate full audio first, then send
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_path = AUDIO_DIR / f"briefing_{briefing.id}_{timestamp}.wav"

                success = await backend.generate_audio(
                    text=briefing.script_text,
                    output_path=output_path,
                    db=db,
                    ref_audio_id=briefing.ref_audio_id,
                )

                if success and output_path.exists():
                    import soundfile as sf
                    audio_data, sr = sf.read(str(output_path))
                    sample_rate = int(sr)
                    audio_bytes = audio_data.astype(np.float32).tobytes()

                    chunk_data = {
                        "type": "chunk",
                        "index": 0,
                        "total": 1,
                        "sample_rate": sample_rate,
                        "audio_base64": base64.b64encode(audio_bytes).decode("utf-8"),
                    }
                    yield f"data: {json.dumps(chunk_data)}\n\n"
                    final_audio_path = str(output_path.relative_to(AUDIO_DIR))

                    # Update briefing record
                    async with async_session() as bg_db:
                        b = await bg_db.get(DailyBriefing, briefing.id)
                        if b:
                            b.audio_path = final_audio_path
                            b.status = "completed"
                            await bg_db.commit()
                else:
                    yield f"data: {json.dumps({'type': 'error', 'message': 'Audio generation failed'})}\n\n"
                    return

            # Signal completion
            yield f"data: {json.dumps({'type': 'done', 'audio_path': final_audio_path})}\n\n"

        except Exception as e:
            logger.error(f"Streaming error for briefing {briefing_id}: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        finally:
            # Always release the lock and update status on completion/error/disconnect
            await _release_streaming_lock(briefing_id)
            # Update status to completed (if we have audio) or failed
            async with async_session() as bg_db:
                b = await bg_db.get(DailyBriefing, briefing.id)
                if b and b.status == "generating":
                    if final_audio_path:
                        b.status = "completed"
                    else:
                        b.status = "failed"
                    await bg_db.commit()

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

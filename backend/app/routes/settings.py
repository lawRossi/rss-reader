"""Settings API routes."""

import json
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db, async_session
from app.models import Setting
from app.schemas import SettingOut, SettingsUpdate, TtsEngineOptions
from app.config import TTS_ENGINE_OPTIONS, AUDIO_DIR

router = APIRouter(prefix="/api/settings", tags=["Settings"])

# Ensure reference audio dir exists
REF_AUDIO_DIR = AUDIO_DIR / "ref_voices"
REF_AUDIO_DIR.mkdir(parents=True, exist_ok=True)


# ─── Helpers ───

async def _get_setting(db: AsyncSession, key: str, default: str = "") -> str:
    result = await db.execute(select(Setting).where(Setting.key == key))
    setting = result.scalar_one_or_none()
    return setting.value if setting else default


async def _set_setting(db: AsyncSession, key: str, value: str):
    existing = await db.get(Setting, key)
    if existing:
        existing.value = value
    else:
        db.add(Setting(key=key, value=value))


async def _get_ref_audios(db: AsyncSession) -> list[dict]:
    """Get all reference audios as a list of dicts."""
    raw = await _get_setting(db, "tts_nano_ref_audios", "[]")
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []


async def _save_ref_audios(db: AsyncSession, audios: list[dict]):
    await _set_setting(db, "tts_nano_ref_audios", json.dumps(audios, ensure_ascii=False))
    # Keep legacy settings in sync for backward compatibility
    active = next((a for a in audios if a.get("active")), None)
    if active:
        active_path = str(REF_AUDIO_DIR / active["filename"])
        await _set_setting(db, "tts_nano_ref_audio", active_path)
        await _set_setting(db, "tts_nano_ref_text", active.get("text", ""))
    await db.flush()


# ─── General Settings ───

@router.get("", response_model=list[SettingOut])
async def get_settings(db: AsyncSession = Depends(get_db)):
    """Get all settings."""
    result = await db.execute(select(Setting))
    settings = result.scalars().all()
    return settings


@router.put("", response_model=list[SettingOut])
async def update_settings(update: SettingsUpdate, db: AsyncSession = Depends(get_db)):
    """Batch update settings."""
    for key, value in update.settings.items():
        existing = await db.get(Setting, key)
        if existing:
            existing.value = value
        else:
            db.add(Setting(key=key, value=value))
    await db.flush()
    result = await db.execute(select(Setting))
    return result.scalars().all()


@router.get("/tts-engines", response_model=TtsEngineOptions)
async def get_tts_engine_options():
    """Get available TTS engine options."""
    return TtsEngineOptions(engines=TTS_ENGINE_OPTIONS)


# ─── Multiple Reference Audios API ───

@router.get("/tts-ref-audios")
async def list_ref_audios(db: AsyncSession = Depends(get_db)):
    """List all reference audios."""
    audios = await _get_ref_audios(db)
    return {"audios": audios}


@router.post("/tts-ref-audios")
async def add_ref_audio(
    name: str = Form(...),
    text: str = Form(""),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Add a new reference audio with name and text."""
    if not file.filename or not file.filename.lower().endswith(('.wav', '.mp3', '.m4a', '.ogg')):
        raise HTTPException(status_code=400, detail="仅支持 WAV/MP3/M4A/OGG 格式")

    if not name.strip():
        raise HTTPException(status_code=400, detail="请填写参考音频名称")

    # Generate unique filename
    ext = Path(file.filename).suffix
    unique_name = f"ref_{uuid.uuid4().hex[:8]}{ext}"
    save_path = REF_AUDIO_DIR / unique_name

    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Build entry
    new_id = uuid.uuid4().hex[:12]
    audios = await _get_ref_audios(db)
    entry = {
        "id": new_id,
        "name": name.strip(),
        "filename": unique_name,
        "text": text.strip(),
        "active": False,
    }
    audios.append(entry)
    await _save_ref_audios(db, audios)

    return {"message": "参考音频已添加", "audio": entry}


@router.put("/tts-ref-audios/{audio_id}")
async def update_ref_audio(
    audio_id: str,
    name: str = Form(None),
    text: str = Form(None),
    file: UploadFile = File(None),
    db: AsyncSession = Depends(get_db),
):
    """Update a reference audio's name, text, or audio file."""
    audios = await _get_ref_audios(db)
    entry = next((a for a in audios if a["id"] == audio_id), None)
    if not entry:
        raise HTTPException(status_code=404, detail="参考音频不存在")

    if name is not None:
        entry["name"] = name.strip()
    if text is not None:
        entry["text"] = text.strip()

    if file and file.filename:
        if not file.filename.lower().endswith(('.wav', '.mp3', '.m4a', '.ogg')):
            raise HTTPException(status_code=400, detail="仅支持 WAV/MP3/M4A/OGG 格式")
        # Remove old file
        old_path = REF_AUDIO_DIR / entry["filename"]
        if old_path.exists():
            old_path.unlink()
        # Save new file
        ext = Path(file.filename).suffix
        unique_name = f"ref_{uuid.uuid4().hex[:8]}{ext}"
        save_path = REF_AUDIO_DIR / unique_name
        with open(save_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        entry["filename"] = unique_name

    await _save_ref_audios(db, audios)
    return {"message": "参考音频已更新", "audio": entry}


@router.delete("/tts-ref-audios/{audio_id}")
async def delete_ref_audio(audio_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a reference audio."""
    audios = await _get_ref_audios(db)
    entry = next((a for a in audios if a["id"] == audio_id), None)
    if not entry:
        raise HTTPException(status_code=404, detail="参考音频不存在")

    # Delete file
    file_path = REF_AUDIO_DIR / entry["filename"]
    if file_path.exists():
        file_path.unlink()

    # Remove from list
    audios = [a for a in audios if a["id"] != audio_id]
    await _save_ref_audios(db, audios)

    return {"message": "参考音频已删除"}


@router.get("/tts-ref-audios/{audio_id}/audio")
async def get_ref_audio_file(audio_id: str, db: AsyncSession = Depends(get_db)):
    """Get a specific reference audio file for playback."""
    audios = await _get_ref_audios(db)
    entry = next((a for a in audios if a["id"] == audio_id), None)
    if not entry:
        raise HTTPException(status_code=404, detail="参考音频不存在")
    file_path = REF_AUDIO_DIR / entry["filename"]
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="音频文件不存在")
    return FileResponse(str(file_path), media_type=f"audio/{file_path.suffix.lstrip('.')}")


@router.post("/tts-ref-audios/{audio_id}/activate")
async def activate_ref_audio(audio_id: str, db: AsyncSession = Depends(get_db)):
    """Set a reference audio as the active one."""
    audios = await _get_ref_audios(db)
    entry = next((a for a in audios if a["id"] == audio_id), None)
    if not entry:
        raise HTTPException(status_code=404, detail="参考音频不存在")

    # Set all to inactive, then activate the target
    for a in audios:
        a["active"] = (a["id"] == audio_id)

    await _save_ref_audios(db, audios)
    return {"message": f"已切换至「{entry['name']}」", "audio": entry}


# ─── Legacy single-file endpoints (backward compatible) ───

@router.post("/tts-ref-audio")
async def upload_tts_ref_audio_legacy(
    file: UploadFile = File(...),
    name: str = Form("用户音色"),
    text: str = Form(""),
):
    """Legacy: upload a reference audio (now handled via /tts-ref-audios)."""
    async with async_session() as db:
        return await add_ref_audio(name=name, text=text, file=file, db=db)


@router.get("/tts-ref-audio")
async def get_tts_ref_audio(db: AsyncSession = Depends(get_db)):
    """Get the active reference audio file."""
    audios = await _get_ref_audios(db)
    active = next((a for a in audios if a.get("active")), audios[0] if audios else None)
    if active:
        file_path = REF_AUDIO_DIR / active["filename"]
        if file_path.exists():
            return FileResponse(str(file_path), media_type=f"audio/{file_path.suffix.lstrip('.')}")
    raise HTTPException(status_code=404, detail="No reference audio available")

"""TTS service — moss-tts-nano only (ONNX voice cloning, single-speaker streaming).

Removed (simplification):
- moss-ttsd (MLX multi-speaker dialogue) backend
- Batch generate_audio() method (streaming-only)
- generate_briefing_audio() top-level function (moved to briefing.py)
"""

import json
import logging
import asyncio
import numpy as np
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Setting
from app.config import AUDIO_DIR

logger = logging.getLogger(__name__)

AUDIO_DIR.mkdir(parents=True, exist_ok=True)


# ─── Helper ───

async def _get_setting(db: AsyncSession, key: str, default: str = "") -> str:
    """Get a setting value from the database."""
    from sqlalchemy import select
    result = await db.execute(select(Setting).where(Setting.key == key))
    setting = result.scalar_one_or_none()
    return setting.value if setting else default


# ─── Abstract Backend ───

class TTSBackend(ABC):
    """Abstract base class for TTS backends."""

    _executor: Optional[ThreadPoolExecutor] = None

    @classmethod
    def _get_executor(cls) -> ThreadPoolExecutor:
        if cls._executor is None:
            cls._executor = ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix=f"tts-{cls.__name__}",
            )
        return cls._executor

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        ...

    @abstractmethod
    async def generate_audio_streaming(
        self, text: str, db: AsyncSession, ref_audio_id: str | None = None
    ) -> AsyncGenerator[tuple[bytes, int, int, int], None]:
        """Async generator yielding audio chunks for streaming playback.

        Each yield: (audio_bytes: bytes, sample_rate: int, index: int, total: int)
        """
        ...


# ─── MossTTSNano Backend (ONNX runtime) ───

_ONNX_TTS_MODEL_DIR = Path(__file__).resolve().parent.parent / "onnx_tts" / "models"


class MossTTSNanoBackend(TTSBackend):
    """MOSS-TTS-Nano via onnxruntime — single-speaker voice cloning from reference audio."""

    _model = None
    _model_lock = asyncio.Lock()
    DEFAULT_REF_AUDIO = AUDIO_DIR / "default_ref_voice.wav"

    @property
    def name(self) -> str:
        return "moss-tts-nano"

    async def is_available(self) -> bool:
        return self._model is not None

    # ── model loading ──

    async def _load_model(self):
        if self._model is not None:
            return self._model
        async with self._model_lock:
            if self._model is not None:
                return self._model
            logger.info("Loading MOSS-TTS-Nano ONNX model...")
            loop = asyncio.get_running_loop()

            def _load():
                import os
                from app.onnx_tts import OnnxTtsRuntime
                return OnnxTtsRuntime(
                    model_dir=str(_ONNX_TTS_MODEL_DIR),
                    thread_count=max(1, os.cpu_count() or 1),
                    max_new_frames=375,
                    do_sample=True,
                    sample_mode="fixed",
                )

            self._model = await loop.run_in_executor(self._get_executor(), _load)
            logger.info("MOSS-TTS-Nano ONNX model loaded successfully.")
            return self._model

    async def _resolve_ref_audio(self, db: AsyncSession,
                                  ref_audio_id: str | None = None) -> Optional[Path]:
        """Resolve reference audio path from settings or use default."""
        raw = await _get_setting(db, "tts_nano_ref_audios", "[]")
        try:
            audios = json.loads(raw)
            if isinstance(audios, list) and audios:
                if ref_audio_id:
                    matched = next((a for a in audios if a.get("id") == ref_audio_id), None)
                    if matched:
                        ref_path = AUDIO_DIR / "ref_voices" / matched["filename"]
                        if ref_path.exists():
                            return ref_path
                        logger.warning(f"Reference audio ID '{ref_audio_id}' file not found: {ref_path}")
                else:
                    active = next((a for a in audios if a.get("active")), audios[0])
                    ref_path = AUDIO_DIR / "ref_voices" / active["filename"]
                    if ref_path.exists():
                        return ref_path
        except (json.JSONDecodeError, TypeError, KeyError):
            pass

        path_str = await _get_setting(db, "tts_nano_ref_audio", "")
        if path_str:
            ref_path = Path(path_str)
            if ref_path.exists():
                return ref_path
            logger.warning(f"Configured ref audio not found: {path_str}")

        if self.DEFAULT_REF_AUDIO.exists():
            return self.DEFAULT_REF_AUDIO

        logger.error("No reference audio available for voice cloning")
        return None

    async def generate_audio_streaming(
        self, text: str, db: AsyncSession, ref_audio_id: str | None = None
    ):
        """Async generator yielding audio chunks for streaming playback.

        Each yield: (audio_bytes: bytes, sample_rate: int, index: int, total: int)
        """
        model = await self._load_model()
        ref_audio = await self._resolve_ref_audio(db, ref_audio_id=ref_audio_id)
        if ref_audio is None:
            return
        clean_text = text.replace("[S1]", "").replace("[S2]", "").strip()

        loop = asyncio.get_running_loop()

        def _prepare():
            chunks = model.split_voice_clone_text(clean_text, max_tokens=75)
            prompt_audio_codes = model.resolve_prompt_audio_codes(
                voice="Junhao",
                prompt_audio_path=str(ref_audio),
            )
            sample_rate = int(model.codec_meta["codec_config"]["sample_rate"])
            return chunks, prompt_audio_codes, sample_rate

        chunks, prompt_audio_codes, sample_rate = await loop.run_in_executor(
            self._get_executor(), _prepare
        )
        total = len(chunks)
        logger.info(f"Streaming {total} chunk(s), {len(clean_text)} chars total")

        CHUNK_TIMEOUT = 300

        for i, chunk_text in enumerate(chunks):
            logger.info(f"Streaming chunk {i + 1}/{total} ({len(chunk_text)} chars)...")

            def _synthesize_chunk(_text=chunk_text):
                result = model.synthesize_single_chunk(
                    text=_text,
                    prompt_audio_codes=prompt_audio_codes,
                )
                return result["waveform"]

            try:
                waveform = await asyncio.wait_for(
                    loop.run_in_executor(self._get_executor(), _synthesize_chunk),
                    timeout=CHUNK_TIMEOUT,
                )
            except asyncio.TimeoutError:
                logger.error(
                    "Streaming chunk %d/%d timed out after %ds",
                    i + 1, total, CHUNK_TIMEOUT,
                )
                continue

            if waveform is None or waveform.size == 0:
                logger.error(f"Streaming chunk {i + 1}/{total} failed (empty waveform)")
                continue

            audio_np = np.asarray(waveform, dtype=np.float32)
            if audio_np.ndim == 2:
                audio_np = audio_np.mean(axis=1)
            yield audio_np.tobytes(), sample_rate, i, total


# ─── Backend Registry (simplified — nano only) ───

_nano_backend: MossTTSNanoBackend | None = None
_nano_backend_lock = asyncio.Lock()


def get_active_backend() -> MossTTSNanoBackend:
    """Return the singleton nano backend (the only backend)."""
    global _nano_backend
    if _nano_backend is None:
        _nano_backend = MossTTSNanoBackend()
    return _nano_backend


async def get_available_backends() -> dict[str, bool]:
    """Check availability of the only backend."""
    backend = get_active_backend()
    try:
        return {"moss-tts-nano": await backend.is_available()}
    except Exception as e:
        logger.warning(f"Backend check failed: {e}")
        return {"moss-tts-nano": False}

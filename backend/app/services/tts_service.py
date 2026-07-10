"""TTS service — supports edge-tts (default) and moss-tts-nano (ONNX voice cloning).

Backends:
  - edge-tts: Microsoft Edge online TTS, high quality, no config needed
  - moss-tts-nano: ONNX-based voice cloning from reference audio (local)
"""

import json
import logging
import asyncio
import miniaudio
import numpy as np
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import Setting
from app.config import AUDIO_DIR

logger = logging.getLogger(__name__)

AUDIO_DIR.mkdir(parents=True, exist_ok=True)


# ─── Helper ───

async def _get_setting(db: AsyncSession, key: str, default: str = "") -> str:
    """Get a setting value from the database."""
    result = await db.execute(select(Setting).where(Setting.key == key))
    setting = result.scalar_one_or_none()
    return setting.value if setting else default


async def _get_setting_raw(key: str, default: str = "") -> str:
    """Get a setting value without DB session (uses a fresh one)."""
    from app.database import async_session
    async with async_session() as db:
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
        self, text: str, db: AsyncSession, ref_audio_id: str | None = None,
        **kwargs,
    ) -> AsyncGenerator[tuple[bytes, int, int, int], None]:
        """Async generator yielding audio chunks for streaming playback.

        Each yield: (audio_bytes: bytes, sample_rate: int, index: int, total: int)

        Kwargs:
            tts_edge_voice: Override voice for edge-tts backend (ignored by nano).
        """
        ...


# ─── Edge TTS Backend (Microsoft Edge online TTS) ───

EDGE_TTS_SAMPLE_RATE = 24000


class EdgeTTSBackend(TTSBackend):
    """Microsoft Edge online TTS via edge-tts library.

    High-quality, natural-sounding speech synthesis with no additional
    configuration required. Supports many voices and languages.

    Uses ffmpeg (via subprocess) to decode MP3 output to PCM float32.
    """

    @property
    def name(self) -> str:
        return "edge-tts"

    async def is_available(self) -> bool:
        """Check if edge-tts and miniaudio are importable."""
        try:
            import edge_tts  # noqa: F401
            import miniaudio  # noqa: F401
            return True
        except ImportError:
            return False

    async def _get_voice(self, db: AsyncSession) -> str:
        """Get the configured voice from settings."""
        return await _get_setting(db, "tts_edge_voice", "zh-CN-XiaoxiaoNeural")

    @staticmethod
    def _split_text(text: str, min_chars: int = 100) -> list[str]:
        """Split text into natural segments for progressive streaming.

        Split by sentence-ending punctuation to produce natural-sounding
        segments. Each segment targets roughly 2-3 sentences.

        Handles Chinese (。！？) and English (.!?) punctuation.

        Args:
            text: The text to split.
            min_chars: Minimum characters per segment. Segments shorter
                       than this will be merged with the next segment.
                       Default 100.
        """
        if not text:
            return []

        # Split on sentence-ending punctuation, keeping the delimiter
        import re
        segments = re.split(r'(?<=[。！？.!?\n])', text)
        segments = [s.strip() for s in segments if s.strip()]

        # Merge very short segments (< 10 chars) into the previous one
        merged = []
        for seg in segments:
            if merged and len(seg) < 10:
                merged[-1] += seg
            else:
                merged.append(seg)

        # Further merge: if a segment is shorter than min_chars and
        # there's a next segment, merge them to avoid many tiny chunks
        final = []
        i = 0
        while i < len(merged):
            if i + 1 < len(merged) and len(merged[i]) < min_chars:
                final.append(merged[i] + merged[i + 1])
                i += 2
            else:
                final.append(merged[i])
                i += 1

        # Fallback: if splitting produced nothing useful, return the whole text
        if not final:
            return [text]

        return final

    async def generate_audio_streaming(
        self, text: str, db: AsyncSession, ref_audio_id: str | None = None,
        **kwargs,
    ):
        """Generate audio using Edge TTS — truly progressive streaming.

        Text is split into natural segments (by sentence boundaries).
        Each segment is independently sent to Edge TTS, decoded via ffmpeg,
        and yielded immediately — so the client receives audio progressively.

        Note: ref_audio_id is ignored for edge-tts (uses preset voices).

        Kwargs:
            tts_edge_voice: Override voice for this generation. If None/empty,
                            falls back to the global tts_edge_voice setting.
        """
        import edge_tts

        # Resolve voice: explicit override > briefing override > global setting
        voice_override = kwargs.get("tts_edge_voice")
        voice = voice_override or await self._get_voice(db)
        segments = self._split_text(text)
        total = len(segments)

        if total == 0:
            logger.warning("Edge TTS: no text segments to process")
            return

        logger.info(
            "Edge TTS streaming %d segment(s) (voice=%s, %d chars total)",
            total, voice, len(text),
        )

        loop = asyncio.get_running_loop()

        for i, segment_text in enumerate(segments):
            logger.debug(
                "Edge TTS segment %d/%d: %d chars",
                i + 1, total, len(segment_text),
            )

            # Generate MP3 for this segment
            communicate = edge_tts.Communicate(segment_text, voice)

            mp3_data = bytearray()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    mp3_data.extend(chunk["data"])

            if not mp3_data:
                logger.warning(
                    "Edge TTS segment %d/%d returned no audio, skipping",
                    i + 1, total,
                )
                continue

            # Decode MP3 → PCM float32 via miniaudio (no external deps needed)
            def _decode_segment(_mp3=bytes(mp3_data)):
                result = miniaudio.decode(
                    _mp3,
                    output_format=miniaudio.SampleFormat.FLOAT32,
                    nchannels=1,
                    sample_rate=EDGE_TTS_SAMPLE_RATE,
                )
                return np.frombuffer(result.samples, dtype=np.float32)

            try:
                pcm_data = await loop.run_in_executor(
                    self._get_executor(), _decode_segment,
                )
            except Exception as e:
                logger.error(
                    "Edge TTS segment %d/%d decoding failed: %s",
                    i + 1, total, e,
                )
                continue

            if pcm_data.size == 0:
                logger.warning(
                    "Edge TTS segment %d/%d decoded PCM is empty",
                    i + 1, total,
                )
                continue

            logger.debug(
                "Edge TTS yielding segment %d/%d: %d samples (%.1fs)",
                i + 1, total,
                len(pcm_data), len(pcm_data) / EDGE_TTS_SAMPLE_RATE,
            )
            yield pcm_data.tobytes(), EDGE_TTS_SAMPLE_RATE, i, total


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
        self, text: str, db: AsyncSession, ref_audio_id: str | None = None,
        **kwargs,
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


# ─── Backend Registry ───

_backends: dict[str, TTSBackend] = {}
_selected_engine: str = "edge-tts"


def _get_or_create_backend(name: str) -> TTSBackend:
    """Get or create a backend instance by name."""
    if name not in _backends:
        if name == "edge-tts":
            _backends[name] = EdgeTTSBackend()
        elif name == "moss-tts-nano":
            _backends[name] = MossTTSNanoBackend()
        else:
            raise ValueError(f"Unknown TTS backend: {name}")
    return _backends[name]


def set_selected_engine(name: str):
    """Set the active TTS engine name globally."""
    global _selected_engine
    if name not in ("edge-tts", "moss-tts-nano"):
        logger.warning(f"Unknown TTS engine '{name}', falling back to edge-tts")
        name = "edge-tts"
    _selected_engine = name


def get_active_backend() -> TTSBackend:
    """Return the singleton backend for the currently selected engine."""
    return _get_or_create_backend(_selected_engine)


async def get_available_backends() -> dict[str, bool]:
    """Check availability of all registered backends."""
    result = {}
    for name in ("edge-tts", "moss-tts-nano"):
        backend = _get_or_create_backend(name)
        try:
            result[name] = await backend.is_available()
        except Exception as e:
            logger.warning(f"Backend '{name}' check failed: {e}")
            result[name] = False
    return result

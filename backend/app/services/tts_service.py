"""TTS service supporting multiple engines with voice cloning.

Supported engines:
- moss-ttsd: Multi-speaker dialogue via mlx-speech (MOSS-TTSD-MLX)
- moss-tts-nano: Voice cloning via ONNX runtime (MOSS-TTS-Nano-100M-ONNX)

Engine selection is configured via the "tts_engine" database setting.
"""

import json
import logging
import asyncio
import numpy as np
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DailyBriefing, Setting
from app.config import AUDIO_DIR

logger = logging.getLogger(__name__)

AUDIO_DIR.mkdir(parents=True, exist_ok=True)


# ─── Helpers ───

async def _get_setting(db: AsyncSession, key: str, default: str = "") -> str:
    """Get a setting value from the database."""
    result = await db.execute(select(Setting).where(Setting.key == key))
    setting = result.scalar_one_or_none()
    return setting.value if setting else default


# ─── Audio Utils ───

def _trim_silence(audio: np.ndarray, threshold: float = 0.02, padding: int = 120) -> np.ndarray:
    """Trim leading and trailing silence from an audio array.

    Args:
        audio: 1D numpy array of float audio samples (range [-1, 1]).
        threshold: Amplitude threshold below which is considered silence.
        padding: Number of samples of padding to keep at each end (default 120 ~ 7.5ms @ 16kHz).

    Returns:
        Trimmed audio array (or original if nothing to trim).
    """
    if audio.ndim > 1:
        audio = np.mean(audio, axis=1)
    # Find first and last sample above threshold
    mask = np.abs(audio) > threshold
    indices = np.where(mask)[0]
    if len(indices) == 0:
        return audio  # all silence, return as-is
    start = max(0, indices[0] - padding)
    end = min(len(audio), indices[-1] + padding)
    return audio[start:end]


# ─── Abstract Backend ───

class TTSBackend(ABC):
    """Abstract base class for TTS backends."""

    _executor: Optional[ThreadPoolExecutor] = None

    @classmethod
    def _get_executor(cls) -> ThreadPoolExecutor:
        """Get or create a dedicated single-thread executor for model operations.
        
        Both MLX (Metal GPU stream is thread-local) and ONNX runtime (internal
        state like RNG and streaming sessions are not thread-safe) require all
        operations for a given model to run on the same thread.
        """
        if cls._executor is None:
            cls._executor = ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix=f"mlx-{cls.__name__}",
            )
        return cls._executor

    @abstractmethod
    async def generate_audio(self, text: str, output_path: Path, db: AsyncSession,
                             ref_audio_id: str | None = None) -> bool:
        """Generate audio from text and save to output_path. Returns True on success.
        
        Args:
            text: The script text to synthesize.
            output_path: Where to save the generated audio file.
            db: Database session.
            ref_audio_id: Override reference audio ID (moss-tts-nano only); None = use global.
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        ...


# ─── MossTTSD Backend (mlx-speech) ───

class MossTTSDMLXBackend(TTSBackend):
    """MOSS-TTSD via mlx-speech — multi-speaker dialogue with [S1]/[S2] markers."""

    _model = None
    _model_lock = asyncio.Lock()

    @property
    def name(self) -> str:
        return "moss-ttsd"

    async def is_available(self) -> bool:
        # Only check if model is already loaded — don't trigger download here.
        return self._model is not None

    async def _load_model(self):
        if self._model is not None:
            return self._model
        async with self._model_lock:
            if self._model is not None:
                return self._model
            import mlx_speech
            logger.info("Loading MOSS-TTSD-MLX model (first time may download weights)...")
            loop = asyncio.get_running_loop()
            self._model = await loop.run_in_executor(
                self._get_executor(), lambda: mlx_speech.tts.load("moss-ttsd")
            )
            logger.info("MOSS-TTSD-MLX model loaded successfully.")
            return self._model

    async def generate_audio(self, text: str, output_path: Path, db: AsyncSession,
                             ref_audio_id: str | None = None) -> bool:
        """Generate audio file using streaming chunked synthesis.

        Splits text by [S1]/[S2] speaker markers and generates each segment
        incrementally, writing to the output file chunk by chunk to avoid
        holding the full waveform in memory.
        """
        import re
        import soundfile as sf

        try:
            model = await self._load_model()
            loop = asyncio.get_running_loop()

            # Split text by speaker markers, preserving markers as separators
            parts = re.split(r'(\[S1\]|\[S2\])', text)
            segments = []
            for i in range(1, len(parts), 2):
                marker = parts[i]
                content = parts[i + 1] if i + 1 < len(parts) else ""
                segments.append(marker + content)
            if not segments:
                # No markers found — treat the whole text as one segment
                segments = [text]

            first = True
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            for idx, seg in enumerate(segments):
                seg = seg.strip()
                if not seg:
                    continue

                def _synthesize_seg(_text=seg):
                    result = model.generate(_text)
                    return result.waveform, result.sample_rate

                waveform, sample_rate = await loop.run_in_executor(
                    self._get_executor(), _synthesize_seg
                )
                waveform = np.asarray(waveform, dtype=np.float32)

                if first:
                    channels = waveform.shape[1] if waveform.ndim == 2 else 1
                    sf_file = sf.SoundFile(
                        str(output_path), mode='w',
                        samplerate=int(sample_rate),
                        channels=int(channels),
                        subtype='PCM_16',
                    )
                    sf_file.write(waveform)
                    first = False
                else:
                    # Insert a short pause between segments for natural flow
                    pause_samples = int(sample_rate * 0.3)  # 300ms pause
                    sf_file.write(np.zeros((pause_samples, channels), dtype=np.float32))
                    sf_file.write(waveform)

            if first:
                logger.error("No audio segments generated")
                return False

            sf_file.close()
            logger.info(f"Audio saved (streaming): {output_path}")
            return True

        except Exception as e:
            logger.error(f"MOSS-TTSD generation error: {e}")
            return False


# ─── MossTTSNano Backend (ONNX runtime) ───

# Path to the local onnx_tts package's model directory
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
        # Only check if model is already loaded — don't trigger download here.
        # Model is loaded on first actual generation.
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
        """Resolve reference audio path from settings or use default.

        Args:
            db: Database session.
            ref_audio_id: If provided, look up this specific audio by ID instead of
                          the globally active one. None means use the global active.
        """
        raw = await _get_setting(db, "tts_nano_ref_audios", "[]")
        try:
            audios = json.loads(raw)
            if isinstance(audios, list) and audios:
                if ref_audio_id:
                    # Look up by specific ID
                    matched = next((a for a in audios if a.get("id") == ref_audio_id), None)
                    if matched:
                        ref_path = AUDIO_DIR / "ref_voices" / matched["filename"]
                        if ref_path.exists():
                            return ref_path
                        logger.warning(f"Reference audio ID '{ref_audio_id}' file not found: {ref_path}")
                else:
                    # Use the globally active one
                    active = next((a for a in audios if a.get("active")), audios[0])
                    ref_path = AUDIO_DIR / "ref_voices" / active["filename"]
                    if ref_path.exists():
                        return ref_path
        except (json.JSONDecodeError, TypeError, KeyError):
            pass

        # Fallback to legacy single setting
        path_str = await _get_setting(db, "tts_nano_ref_audio", "")
        if path_str:
            ref_path = Path(path_str)
            if ref_path.exists():
                return ref_path
            logger.warning(f"Configured ref audio not found: {path_str}")

        # Fall back to default
        if self.DEFAULT_REF_AUDIO.exists():
            return self.DEFAULT_REF_AUDIO

        logger.error("No reference audio available for voice cloning")
        return None

    async def _synthesize_text(self, text: str, db: AsyncSession,
                                ref_audio_id: str | None = None):
        """Shared core: chunk text by token budget, synthesize each on executor thread.

        Yields (audio_data: np.ndarray, sample_rate: int) for each chunk.
        Uses the ONNX runtime's built-in token-aware chunking for optimal quality.

        Args:
            text: The script text to synthesize.
            db: Database session.
            ref_audio_id: Override reference audio ID; None = use globally active one.
        """
        model = await self._load_model()
        ref_audio = await self._resolve_ref_audio(db, ref_audio_id=ref_audio_id)
        if ref_audio is None:
            return
        clean_text = text.replace("[S1]", "").replace("[S2]", "").strip()

        loop = asyncio.get_running_loop()

        # Prepare (chunking + reference encoding) inside executor for thread-safety
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
        logger.info(f"Synthesizing {len(chunks)} chunk(s), {len(clean_text)} chars total")

        CHUNK_TIMEOUT = 1200  # 20 minutes per chunk max

        for i, chunk_text in enumerate(chunks):
            logger.info(f"Chunk {i + 1}/{len(chunks)} ({len(chunk_text)} chars)...")

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
                    "Chunk %d/%d timed out after %ds",
                    i + 1, len(chunks), CHUNK_TIMEOUT,
                )
                continue

            if waveform is None or waveform.size == 0:
                logger.error(f"Chunk {i + 1}/{len(chunks)} failed (empty waveform)")
                continue

            yield (np.asarray(waveform, dtype=np.float32), sample_rate)

    async def generate_audio(self, text: str, output_path: Path, db: AsyncSession,
                             ref_audio_id: str | None = None) -> bool:
        """Generate audio file using streaming chunked synthesis.

        Uses _synthesize_text (chunked async generator) to synthesize each
        chunk incrementally and write to file chunk by chunk, instead of
        accumulating the full waveform in memory.

        Args:
            text: The script text to synthesize.
            output_path: Where to save the generated audio file.
            db: Database session.
            ref_audio_id: Override reference audio ID; None = use globally active one.
        """
        import os
        import soundfile as sf

        try:
            first = True
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            sf_file = None

            async for audio_data, sample_rate in self._synthesize_text(text, db, ref_audio_id=ref_audio_id):
                audio_data = np.asarray(audio_data, dtype=np.float32)

                if first:
                    channels = audio_data.shape[1] if audio_data.ndim == 2 else 1
                    sf_file = sf.SoundFile(
                        str(output_path), mode='w',
                        samplerate=int(sample_rate),
                        channels=int(channels),
                        subtype='PCM_16',
                    )
                    sf_file.write(audio_data)
                    first = False
                else:
                    sf_file.write(audio_data)

            if first:
                logger.error("No audio chunks generated")
                return False

            if sf_file:
                sf_file.flush()
                sf_file.close()
                # fsync file to disk — critical before potential OOM kill
                try:
                    fd = os.open(str(output_path), os.O_RDONLY)
                    os.fsync(fd)
                    os.close(fd)
                except OSError:
                    pass
            logger.info("Audio saved (streaming): %s", output_path)
            # Flush all logging handlers so the "saved" message is on disk
            for handler in logging.getLogger().handlers:
                handler.flush()
            return True

        except BaseException as e:
            logger.error("Audio generation failed: %s", e, exc_info=True)
            # Try to close the file if it was opened (partial data)
            if sf_file is not None:
                try:
                    sf_file.flush()
                    sf_file.close()
                except Exception:
                    pass
            for handler in logging.getLogger().handlers:
                handler.flush()
            return False

    async def generate_audio_streaming(self, text: str, db: AsyncSession,
                                        ref_audio_id: str | None = None):
        """Async generator yielding audio chunks for streaming playback.

        Each chunk is yielded as soon as it's synthesized (progressive playback).
        Each yield: (audio_bytes: bytes, sample_rate: int, index: int, total: int)

        Args:
            text: The script text to synthesize.
            db: Database session.
            ref_audio_id: Override reference audio ID; None = use globally active one.
        """
        model = await self._load_model()
        ref_audio = await self._resolve_ref_audio(db, ref_audio_id=ref_audio_id)
        if ref_audio is None:
            return
        clean_text = text.replace("[S1]", "").replace("[S2]", "").strip()

        loop = asyncio.get_running_loop()

        # Prepare (chunking + reference encoding) inside executor for thread-safety
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

        CHUNK_TIMEOUT = 1200  # 20 minutes per chunk max

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
            # ONNX model may output stereo (samples, 2). Convert to mono for streaming.
            if audio_np.ndim == 2:
                audio_np = audio_np.mean(axis=1)
            yield audio_np.tobytes(), sample_rate, i, total


# ─── Backend Registry ───

_backends: dict[str, TTSBackend] = {}
_backends_lock = asyncio.Lock()


def _get_backends() -> dict[str, TTSBackend]:
    """Get or create all registered backends."""
    global _backends
    if not _backends:
        _backends = {
            "moss-ttsd": MossTTSDMLXBackend(),
            "moss-tts-nano": MossTTSNanoBackend(),
        }
    return _backends


async def get_active_backend(db: AsyncSession) -> TTSBackend:
    """Get the currently configured TTS backend based on settings."""
    engine = await _get_setting(db, "tts_engine", "moss-ttsd")
    backends = _get_backends()
    if engine not in backends:
        logger.warning(f"Unknown TTS engine '{engine}', falling back to moss-ttsd")
        engine = "moss-ttsd"
    return backends[engine]


async def get_available_backends(db: AsyncSession) -> dict[str, bool]:
    """Check availability of all backends."""
    backends = _get_backends()
    result = {}
    for name, backend in backends.items():
        try:
            result[name] = await backend.is_available()
        except Exception as e:
            logger.warning(f"Backend {name} check failed: {e}")
            result[name] = False
    return result


# ─── Public API (backward compatible) ───

async def check_moss_ttsd_available() -> bool:
    """Check if default TTS backend (moss-ttsd) is available."""
    backend = MossTTSDMLXBackend()
    return await backend.is_available()


async def generate_briefing_audio(briefing_id: int, db: AsyncSession | None = None,
                                  ref_audio_id: str | None = None):
    """Generate audio for a briefing using the configured TTS engine. Runs in background.

    Args:
        briefing_id: The DailyBriefing record ID.
        db: Database session (optional — creates its own if None).
        ref_audio_id: Override reference audio ID; None = use globally active one.
    """
    from app.database import async_session
    async with async_session() as bg_db:
        try:
            briefing = await bg_db.get(DailyBriefing, briefing_id)
            if not briefing:
                logger.error(f"Briefing {briefing_id} not found")
                return

            if not briefing.script_text or briefing.script_text in ("暂无新闻更新。", ""):
                briefing.status = "completed"
                await bg_db.commit()
                return

            briefing.status = "generating"
            await bg_db.commit()

            # Get the active backend
            backend = await get_active_backend(bg_db)
            logger.info(f"Using TTS engine: {backend.name}")

            # Prepare output path
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = AUDIO_DIR / f"briefing_{briefing.id}_{timestamp}.wav"

            # Generate audio — pass ref_audio_id for nano backend
            success = await backend.generate_audio(
                text=briefing.script_text,
                output_path=output_path,
                db=bg_db,
                ref_audio_id=ref_audio_id,
            )

            if success and output_path.exists():
                briefing.audio_path = str(output_path.relative_to(AUDIO_DIR))
                briefing.status = "completed"
                logger.info(f"Audio generated successfully ({backend.name}): {output_path}")
            else:
                briefing.status = "failed"
                briefing.script_text += f"\n\n[音频生成失败 - {backend.name}]"
                logger.error(f"Audio generation failed for briefing {briefing_id} ({backend.name})")

            await bg_db.commit()

        except Exception as e:
            logger.error(f"TTS generation failed for briefing {briefing_id}: {e}")
            try:
                briefing = await bg_db.get(DailyBriefing, briefing_id)
                if briefing:
                    briefing.status = "failed"
                    await bg_db.commit()
            except Exception:
                pass

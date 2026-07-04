"""Application configuration."""

import os
from pathlib import Path

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = BASE_DIR / "backend"
AUDIO_DIR = BASE_DIR / "audio"

# Database
DATABASE_URL = f"sqlite+aiosqlite:///{BACKEND_DIR}/rss_reader.db"

# Server
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# Ensure directories exist
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# Default LLM settings
DEFAULT_LLM_SETTINGS = {
    "llm_api_endpoint": "https://api.openai.com/v1",
    "llm_api_key": "",
    "llm_model_name": "gpt-3.5-turbo",
    "llm_max_tokens": "1024",
    "llm_temperature": "0.7",
}

# Default TTS settings (moss-tts-nano only; moss-ttsd removed in simplification)
DEFAULT_TTS_SETTINGS = {
    "tts_nano_ref_audios": "[]",       # JSON array of [{id, name, filename, text, active}]
    "tts_nano_ref_audio": "",          # Legacy single ref audio path
    "tts_nano_ref_text": "",           # Legacy single ref audio text
    "tts_nano_temperature": "0.5",     # Generation temperature (0.3-0.6 recommended)
}

# TTS engine info (single engine)
TTS_ENGINE_INFO = {
    "label": "MOSS-TTS-Nano (音色克隆)",
    "description": "基于参考音频克隆音色，单人播报，自然流畅",
}

# Default fetch settings
DEFAULT_FETCH_SETTINGS = {
    "fetch_interval": "30",  # RSS feed fetch interval in minutes
}

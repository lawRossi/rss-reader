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

# Default TTS settings
DEFAULT_TTS_SETTINGS = {
    "tts_engine": "moss-ttsd",        # "moss-ttsd" (多主播对话) 或 "moss-tts-nano" (音色克隆)
    "tts_nano_ref_audios": "[]",       # JSON 数组，多个参考音频 [{id, name, filename, text, active}]
    "tts_nano_ref_audio": "",          # 兼容旧版，当前激活的参考音频路径
    "tts_nano_ref_text": "",           # 兼容旧版，当前参考音频文本
    "tts_nano_temperature": "0.5",     # 生成温度（音色克隆建议 0.3-0.6，越低越稳定）
}

# Default fetch settings
DEFAULT_FETCH_SETTINGS = {
    "fetch_interval": "30",  # RSS feed fetch interval in minutes
}

# TTS engine options
TTS_ENGINE_OPTIONS = {
    "moss-ttsd": {
        "label": "MOSS-TTSD (多主播对话)",
        "description": "使用 [S1]/[S2] 标记生成双人对播，无需参考音频",
    },
    "moss-tts-nano": {
        "label": "MOSS-TTS-Nano (音色克隆)",
        "description": "基于参考音频克隆音色，单人播报，自然流畅",
    },
}

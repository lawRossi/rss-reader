"""DailyBriefing model for podcast-style news summaries."""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime
from app.database import Base


class DailyBriefing(Base):
    __tablename__ = "daily_briefings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String(10), nullable=False)  # YYYY-MM-DD
    title = Column(String(255), default="")
    content_json = Column(Text, default="[]")  # JSON list of article info
    script_text = Column(Text, default="")     # Podcast script with [S1]/[S2] markers
    audio_path = Column(String(1024), default="")
    status = Column(String(20), default="pending")  # pending, generating, completed, failed
    ref_audio_id = Column(String(50), nullable=True)  # Override reference audio; None = use global
    tts_edge_voice = Column(String(100), nullable=True)  # Override Edge TTS voice; None = use global
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<DailyBriefing(id={self.id}, date={self.date}, status={self.status})>"

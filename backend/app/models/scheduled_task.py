"""ScheduledTask model for automatic daily briefing generation."""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from app.database import Base


class ScheduledTask(Base):
    __tablename__ = "scheduled_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    cron_expr = Column(String(50), nullable=False)  # e.g. "0 8 * * *" = daily at 08:00
    time_range = Column(String(10), default="today")  # "today", "12h", "24h"
    group_id = Column(Integer, nullable=True)  # null = all groups
    include_audio = Column(Boolean, default=True)
    ref_audio_id = Column(String(50), nullable=True)  # Override reference audio; None = use global
    tts_edge_voice = Column(String(100), nullable=True)  # Override Edge TTS voice; None = use global
    enabled = Column(Boolean, default=True)
    last_run_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<ScheduledTask(id={self.id}, name={self.name}, cron='{self.cron_expr}', enabled={self.enabled})>"

"""Feed model for RSS sources."""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class Feed(Base):
    __tablename__ = "feeds"

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(255), default="")
    url = Column(String(1024), nullable=False, unique=True)
    site_url = Column(String(1024), default="")
    description = Column(Text, default="")
    icon = Column(String(1024), default="")
    last_fetched_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    group = relationship("Group", backref="feeds")
    articles = relationship("Article", backref="feed", cascade="all, delete-orphan",
                            passive_deletes=True)

    def __repr__(self):
        return f"<Feed(id={self.id}, title={self.title})>"

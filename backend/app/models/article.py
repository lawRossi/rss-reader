"""Article model for RSS entries."""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class Article(Base):
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    feed_id = Column(Integer, ForeignKey("feeds.id", ondelete="CASCADE"), nullable=False)
    guid = Column(String(1024), default="")
    title = Column(String(512), default="")
    url = Column(String(1024), default="")
    author = Column(String(255), default="")
    content = Column(Text, default="")
    summary = Column(Text, default="")
    content_type = Column(String(50), default="html")
    is_read = Column(Boolean, default=False)
    is_starred = Column(Boolean, default=False)
    published_at = Column(DateTime, nullable=True)
    fetched_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    tags = relationship("Tag", secondary="article_tags", backref="articles")

    def __repr__(self):
        return f"<Article(id={self.id}, title={self.title})>"

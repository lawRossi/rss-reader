"""Article-Tag association model."""

from sqlalchemy import Column, Integer, ForeignKey, UniqueConstraint
from app.database import Base


class ArticleTag(Base):
    __tablename__ = "article_tags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    article_id = Column(Integer, ForeignKey("articles.id", ondelete="CASCADE"), nullable=False)
    tag_id = Column(Integer, ForeignKey("tags.id", ondelete="CASCADE"), nullable=False)

    __table_args__ = (
        UniqueConstraint("article_id", "tag_id", name="uq_article_tag"),
    )

    def __repr__(self):
        return f"<ArticleTag(article_id={self.article_id}, tag_id={self.tag_id})>"

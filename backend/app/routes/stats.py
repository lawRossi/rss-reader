"""Statistics API routes for homepage dashboard."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models import Article, Feed

router = APIRouter(prefix="/api/stats", tags=["Stats"])


@router.get("")
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Get dashboard statistics.

    Returns:
        - today_count: number of articles created today
        - starred_count: total number of starred articles
        - unread_count: total number of unread articles
        - feed_count: total number of feeds
    """
    # Today's new articles count (based on created_at)
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_count = await db.scalar(
        select(func.count(Article.id)).where(Article.created_at >= today_start)
    )

    # Total starred articles count
    starred_count = await db.scalar(
        select(func.count(Article.id)).where(Article.is_starred == True)
    )

    # Total unread articles count
    unread_count = await db.scalar(
        select(func.count(Article.id)).where(Article.is_read == False)
    )

    # Total feeds count
    feed_count = await db.scalar(select(func.count(Feed.id)))

    return {
        "today_count": today_count or 0,
        "starred_count": starred_count or 0,
        "unread_count": unread_count or 0,
        "feed_count": feed_count or 0,
    }

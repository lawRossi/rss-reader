"""RSS feed fetching and article extraction service."""

import logging
import asyncio
from datetime import datetime, timezone

import feedparser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Feed, Article

logger = logging.getLogger(__name__)


async def fetch_and_save_articles(db: AsyncSession, feed: Feed) -> int:
    """Fetch articles from a feed and save new ones. Returns count of new articles."""
    try:
        parsed = feedparser.parse(feed.url)
    except Exception as e:
        logger.error(f"Error parsing feed {feed.url}: {e}")
        return 0

    # Update feed metadata if empty
    if not feed.title and hasattr(parsed.feed, "title"):
        feed.title = parsed.feed.title
    if not feed.site_url and hasattr(parsed.feed, "link"):
        feed.site_url = parsed.feed.link

    new_count = 0
    for entry in parsed.entries:
        guid = entry.get("id", entry.get("link", ""))
        if not guid:
            continue

        # Check if article already exists
        existing = await db.execute(
            select(Article).where(
                Article.feed_id == feed.id,
                Article.guid == guid,
            )
        )
        if existing.scalar_one_or_none():
            continue

        title = entry.get("title", "Untitled")
        url = entry.get("link", "")
        author = entry.get("author", "")
        content = _extract_content(entry)
        published = _parse_date(entry)

        article = Article(
            feed_id=feed.id,
            guid=guid,
            title=title,
            url=url,
            author=author,
            content=content,
            published_at=published,
        )
        db.add(article)
        new_count += 1

    # Update last_fetched_at
    feed.last_fetched_at = datetime.now(timezone.utc)
    await db.flush()

    logger.info(f"Fetched {new_count} new articles from {feed.title}")
    return new_count


def _extract_content(entry) -> str:
    """Extract HTML content from a feed entry."""
    # Try common content fields
    if hasattr(entry, "content") and entry.content:
        for c in entry.content:
            if c.get("type", "").startswith("text/html"):
                return c.get("value", "")
    if hasattr(entry, "description"):
        return entry.description
    if hasattr(entry, "summary"):
        return entry.summary
    return ""


def _parse_date(entry):
    """Parse published/updated date from entry.

    feedparser's ``published_parsed`` is a ``time.struct_time`` in **UTC**,
    so we use ``calendar.timegm()`` (not ``mktime`` which assumes local time).
    """
    for field in ["published_parsed", "updated_parsed"]:
        if hasattr(entry, field) and getattr(entry, field):
            try:
                import calendar
                return datetime.fromtimestamp(
                    calendar.timegm(getattr(entry, field)), tz=timezone.utc
                )
            except Exception:
                pass
    return None


# ─── Background periodic fetching ───

_background_task = None


async def start_periodic_fetch(interval_minutes: int = 30):
    """Start background task to periodically fetch all feeds."""
    global _background_task
    if _background_task is not None:
        _background_task.cancel()

    async def _run():
        while True:
            try:
                await _fetch_all_feeds()
            except Exception as e:
                logger.error(f"Periodic fetch error: {e}")
            await asyncio.sleep(interval_minutes * 60)

    _background_task = asyncio.create_task(_run())
    logger.info(f"Started periodic fetch every {interval_minutes} minutes")


async def _fetch_all_feeds():
    """Fetch all feeds in the background."""
    from app.database import async_session
    async with async_session() as db:
        try:
            result = await db.execute(select(Feed))
            feeds = result.scalars().all()
            for feed in feeds:
                try:
                    await fetch_and_save_articles(db, feed)
                except Exception as e:
                    logger.error(f"Error fetching feed {feed.id} ({feed.title}): {e}")
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error(f"Background fetch error: {e}")

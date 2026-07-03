"""OPML file import service."""

import logging
import xml.etree.ElementTree as ET
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Group, Feed

logger = logging.getLogger(__name__)


class OpmlImportResult:
    def __init__(self):
        self.success_count = 0
        self.fail_count = 0
        self.failures: list[dict] = []
        self.group_count = 0


async def import_opml(db: AsyncSession, opml_content: str) -> OpmlImportResult:
    """Parse OPML content and import feeds.

    OPML format:
    <opml>
      <body>
        <outline text="GroupName">
          <outline type="rss" text="Feed Title" xmlUrl="https://..." htmlUrl="https://..."/>
        </outline>
        <outline type="rss" text="Ungrouped Feed" xmlUrl="https://..."/>
      </body>
    </opml>
    """
    result = OpmlImportResult()

    try:
        root = ET.fromstring(opml_content)
    except ET.ParseError as e:
        result.fail_count = 1
        result.failures.append({"url": "N/A", "reason": f"Invalid OPML XML: {e}"})
        return result

    body = root.find("body")
    if body is None:
        result.fail_count = 1
        result.failures.append({"url": "N/A", "reason": "OPML has no <body> element"})
        return result

    # Process each top-level outline
    for outline in body.findall("outline"):
        group_name = outline.get("text", outline.get("title", ""))

        # Check if this outline has children (it's a group)
        children = outline.findall("outline")
        if children:
            # Create group
            group = None
            if group_name:
                from sqlalchemy import select
                existing = await db.execute(
                    select(Group).where(Group.name == group_name)
                )
                group = existing.scalar_one_or_none()
                if not group:
                    group = Group(name=group_name, sort_order=0)
                    db.add(group)
                    await db.flush()
                    result.group_count += 1

            # Process feeds in this group
            for child in children:
                await _process_feed_outline(db, child, group.id if group else None, result)
        else:
            # Ungrouped feed
            await _process_feed_outline(db, outline, None, result)

    await db.flush()
    return result


async def _process_feed_outline(
    db: AsyncSession,
    outline: ET.Element,
    group_id: Optional[int],
    result: OpmlImportResult,
):
    """Process a single feed outline element."""
    feed_url = outline.get("xmlUrl", "")
    if not feed_url:
        # Some OPML use 'url' instead
        feed_url = outline.get("url", "")

    if not feed_url:
        result.fail_count += 1
        result.failures.append({
            "url": outline.get("text", "Unknown"),
            "reason": "No RSS URL found",
        })
        return

    title = outline.get("text", outline.get("title", feed_url))
    site_url = outline.get("htmlUrl", "")

    try:
        # Check if feed already exists
        from sqlalchemy import select
        existing = await db.execute(select(Feed).where(Feed.url == feed_url))
        if existing.scalar_one_or_none():
            result.fail_count += 1
            result.failures.append({
                "url": feed_url,
                "reason": "Feed already exists",
            })
            return

        # Try to fetch feed metadata
        import feedparser
        try:
            parsed = feedparser.parse(feed_url)
            feed_info = parsed.feed
            if hasattr(feed_info, "title") and feed_info.title:
                title = feed_info.title
            if hasattr(feed_info, "link") and feed_info.link:
                site_url = feed_info.link
        except Exception:
            pass

        feed = Feed(
            group_id=group_id,
            title=title,
            url=feed_url,
            site_url=site_url,
        )
        db.add(feed)
        result.success_count += 1

    except Exception as e:
        logger.error(f"Error importing feed {feed_url}: {e}")
        result.fail_count += 1
        result.failures.append({
            "url": feed_url,
            "reason": str(e)[:100],
        })

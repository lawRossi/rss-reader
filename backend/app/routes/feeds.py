"""Feeds API routes."""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from sqlalchemy.orm import joinedload

from app.database import get_db
from app.models import Feed, Group, Article
from app.schemas import FeedCreate, FeedUpdate, FeedOut

router = APIRouter(prefix="/api/feeds", tags=["Feeds"])


@router.get("", response_model=list[FeedOut])
async def list_feeds(db: AsyncSession = Depends(get_db)):
    """List all feeds with group name and article count."""
    result = await db.execute(
        select(
            Feed,
            Group.name.label("group_name"),
            func.count(Article.id).label("article_count"),
        )
        .outerjoin(Group, Feed.group_id == Group.id)
        .outerjoin(Article, Article.feed_id == Feed.id)
        .group_by(Feed.id)
        .order_by(Feed.title)
    )
    rows = result.all()
    feeds_out = []
    for feed, group_name, article_count in rows:
        f = FeedOut.model_validate(feed)
        f.group_name = group_name
        f.article_count = article_count
        feeds_out.append(f)
    return feeds_out


@router.post("", response_model=FeedOut, status_code=201)
async def create_feed(data: FeedCreate, db: AsyncSession = Depends(get_db)):
    """Add a new RSS feed."""
    # Check if feed URL already exists
    existing = await db.execute(select(Feed).where(Feed.url == data.url))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Feed URL already exists")

    # Try to fetch feed info
    import feedparser
    try:
        parsed = feedparser.parse(data.url)
        feed_info = parsed.feed
        title = getattr(feed_info, "title", data.url)
        site_url = getattr(feed_info, "link", "")
        description = getattr(feed_info, "description", "")
        # Try to get icon/favicon
        icon = ""
        if hasattr(feed_info, "image") and hasattr(feed_info.image, "href"):
            icon = feed_info.image.href
    except Exception:
        title = data.url
        site_url = ""
        description = ""
        icon = ""

    feed = Feed(
        group_id=data.group_id,
        title=title,
        url=data.url,
        site_url=site_url,
        description=description,
        icon=icon,
    )
    db.add(feed)
    await db.flush()
    await db.refresh(feed)
    return FeedOut.model_validate(feed)


@router.post("/import-opml")
async def import_opml(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Import feeds from an OPML file."""
    from app.services.opml_importer import import_opml as opml_import_service

    if not file.filename or not file.filename.lower().endswith((".opml", ".xml")):
        raise HTTPException(status_code=400, detail="Please upload an OPML (.opml) file")

    content = await file.read()
    try:
        text_content = content.decode("utf-8")
    except UnicodeDecodeError:
        text_content = content.decode("utf-8", errors="replace")

    result = await opml_import_service(db, text_content)

    return {
        "message": f"Import completed: {result.success_count} succeeded, {result.fail_count} failed, {result.group_count} groups created",
        "success_count": result.success_count,
        "fail_count": result.fail_count,
        "group_count": result.group_count,
        "failures": result.failures,
    }


@router.get("/{feed_id}", response_model=FeedOut)
async def get_feed(feed_id: int, db: AsyncSession = Depends(get_db)):
    """Get feed details."""
    result = await db.execute(
        select(Feed, Group.name.label("group_name"))
        .outerjoin(Group, Feed.group_id == Group.id)
        .where(Feed.id == feed_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Feed not found")
    feed, group_name = row
    # Count articles
    count_result = await db.execute(
        select(func.count(Article.id)).where(Article.feed_id == feed_id)
    )
    article_count = count_result.scalar()
    f = FeedOut.model_validate(feed)
    f.group_name = group_name
    f.article_count = article_count
    return f


@router.put("/{feed_id}", response_model=FeedOut)
async def update_feed(feed_id: int, data: FeedUpdate, db: AsyncSession = Depends(get_db)):
    """Update a feed."""
    feed = await db.get(Feed, feed_id)
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")
    # Use exclude_unset to only apply fields that were explicitly sent
    update_data = data.model_dump(exclude_unset=True)
    if "title" in update_data:
        feed.title = update_data["title"]
    if "url" in update_data:
        feed.url = update_data["url"]
    if "group_id" in update_data:
        feed.group_id = update_data["group_id"]  # May be None (to ungroup)
    await db.flush()
    await db.refresh(feed)
    return FeedOut.model_validate(feed)


@router.delete("/{feed_id}")
async def delete_feed(feed_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a feed and its articles."""
    feed = await db.get(Feed, feed_id)
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")
    # Explicitly delete all articles belonging to this feed first
    # (handles cases where DB-level cascade is not set up)
    await db.execute(
        delete(Article).where(Article.feed_id == feed_id)
    )
    await db.delete(feed)
    await db.flush()
    return {"message": "Feed and associated articles deleted"}


@router.post("/{feed_id}/fetch")
async def fetch_feed(feed_id: int, db: AsyncSession = Depends(get_db)):
    """Manually trigger feed fetch."""
    from app.services.feed_fetcher import fetch_and_save_articles
    feed = await db.get(Feed, feed_id)
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")
    count = await fetch_and_save_articles(db, feed)
    return {"message": f"Fetched {count} new articles"}

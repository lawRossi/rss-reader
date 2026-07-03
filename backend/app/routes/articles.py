"""Articles API routes."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, delete
from sqlalchemy.orm import joinedload, selectinload, contains_eager

from app.database import get_db
from app.models import Article, Feed, Tag, ArticleTag
from app.schemas import (
    ArticleOut, ArticleListItem, ArticleUpdate, BatchAction, PaginatedResponse
)
from app.services.content_fetcher import fetch_full_content

router = APIRouter(prefix="/api/articles", tags=["Articles"])


@router.get("", response_model=PaginatedResponse)
async def list_articles(
    feed_id: int = Query(None),
    group_id: int = Query(None),
    is_read: bool = Query(None),
    is_starred: bool = Query(None),
    tag_id: int = Query(None),
    keyword: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort: str = Query("published_at", pattern="^(published_at|created_at|fetched_at)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
):
    """List articles with filtering and pagination."""
    # Build query
    query = (
        select(Article)
        .outerjoin(Feed, Article.feed_id == Feed.id)
        .options(contains_eager(Article.feed), selectinload(Article.tags))
    )

    # Apply filters
    if feed_id is not None:
        query = query.where(Article.feed_id == feed_id)
    if group_id is not None:
        query = query.where(Feed.group_id == group_id)
    if is_read is not None:
        query = query.where(Article.is_read == is_read)
    if is_starred is not None:
        query = query.where(Article.is_starred == is_starred)
    if tag_id is not None:
        query = query.where(Article.tags.any(Tag.id == tag_id))
    if keyword:
        query = query.where(
            or_(
                Article.title.ilike(f"%{keyword}%"),
                Article.content.ilike(f"%{keyword}%"),
                Article.summary.ilike(f"%{keyword}%"),
            )
        )

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()

    # Apply sorting
    sort_col = getattr(Article, sort, Article.published_at)
    order_func = sort_col.desc() if order == "desc" else sort_col.asc()
    query = query.order_by(order_func)

    # Pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    articles = result.scalars().unique().all()

    # Build response items
    items = []
    for article in articles:
        item = ArticleListItem.model_validate(article)
        item.feed_title = article.feed.title if article.feed else None
        item.feed_icon = article.feed.icon if article.feed else None
        item.tags = [{"id": t.id, "name": t.name, "color": t.color} for t in article.tags]
        items.append(item)

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=max(1, (total + page_size - 1) // page_size),
    )


@router.get("/{article_id}", response_model=ArticleOut)
async def get_article(article_id: int, db: AsyncSession = Depends(get_db)):
    """Get article details."""
    result = await db.execute(
        select(Article)
        .outerjoin(Feed, Article.feed_id == Feed.id)
        .options(contains_eager(Article.feed), selectinload(Article.tags))
        .where(Article.id == article_id)
    )
    article = result.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    out = ArticleOut.model_validate(article)
    out.feed_title = article.feed.title if article.feed else None
    out.tags = [{"id": t.id, "name": t.name, "color": t.color} for t in article.tags]
    return out


@router.patch("/{article_id}", response_model=ArticleOut)
async def update_article(
    article_id: int, data: ArticleUpdate, db: AsyncSession = Depends(get_db)
):
    """Update article (read/star status)."""
    result = await db.execute(
        select(Article)
        .outerjoin(Feed, Article.feed_id == Feed.id)
        .options(contains_eager(Article.feed), selectinload(Article.tags))
        .where(Article.id == article_id)
    )
    article = result.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    if data.is_read is not None:
        article.is_read = data.is_read
    if data.is_starred is not None:
        article.is_starred = data.is_starred
    await db.flush()

    # Re-query to get fresh data with eager-loaded relationships
    result = await db.execute(
        select(Article)
        .outerjoin(Feed, Article.feed_id == Feed.id)
        .options(contains_eager(Article.feed), selectinload(Article.tags))
        .where(Article.id == article_id)
    )
    article = result.scalar_one_or_none()

    out = ArticleOut.model_validate(article)
    out.feed_title = article.feed.title if article.feed else None
    out.tags = [{"id": t.id, "name": t.name, "color": t.color} for t in article.tags]
    return out


@router.post("/{article_id}/fetch-content")
async def fetch_article_content(article_id: int, db: AsyncSession = Depends(get_db)):
    """Fetch full article content from original URL.

    If fetching fails (network error, timeout, etc.), the existing content
    is preserved. The fetched content is also compared with the original:
    if it's not significantly longer, the original is kept.
    """
    result = await db.execute(
        select(Article)
        .outerjoin(Feed, Article.feed_id == Feed.id)
        .options(contains_eager(Article.feed), selectinload(Article.tags))
        .where(Article.id == article_id)
    )
    article = result.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    if not article.url:
        return {
            "content": article.content,
            "source": "existing",
            "note": "Article has no URL, using existing content",
        }

    fetched = await fetch_full_content(article.url)
    if fetched is None:
        return {
            "content": article.content,
            "source": "existing",
            "note": "Failed to fetch from original URL, using existing content",
        }

    # Prefer whichever content is more substantial (by raw HTML length)
    if len(fetched) < len(article.content):
        return {
            "content": article.content,
            "source": "existing",
            "note": "Fetched content was shorter than existing, keeping original",
        }

    # Save fetched content to database
    article.content = fetched
    await db.flush()

    return {
        "content": fetched,
        "source": "fetched",
        "note": None,
    }


@router.post("/batch")
async def batch_action(data: BatchAction, db: AsyncSession = Depends(get_db)):
    """Batch action on articles."""
    result = await db.execute(
        select(Article)
        .options(selectinload(Article.tags))
        .where(Article.id.in_(data.article_ids))
    )
    articles = result.scalars().all()

    for article in articles:
        if data.action == "mark_read":
            article.is_read = True
        elif data.action == "mark_unread":
            article.is_read = False
        elif data.action == "star":
            article.is_starred = True
        elif data.action == "unstar":
            article.is_starred = False

    await db.flush()
    return {"message": f"Updated {len(articles)} articles"}

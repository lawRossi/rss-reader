"""Tags API routes."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models import Tag, Article, ArticleTag
from app.schemas import TagCreate, TagUpdate, TagOut, ArticleTagsUpdate

router = APIRouter(prefix="/api/tags", tags=["Tags"])


@router.get("", response_model=list[TagOut])
async def list_tags(db: AsyncSession = Depends(get_db)):
    """List all tags with article count."""
    result = await db.execute(
        select(
            Tag,
            func.count(ArticleTag.article_id).label("article_count"),
        )
        .outerjoin(ArticleTag, Tag.id == ArticleTag.tag_id)
        .group_by(Tag.id)
        .order_by(Tag.name)
    )
    rows = result.all()
    tags_out = []
    for tag, article_count in rows:
        t = TagOut.model_validate(tag)
        t.article_count = article_count
        tags_out.append(t)
    return tags_out


@router.post("", response_model=TagOut, status_code=201)
async def create_tag(data: TagCreate, db: AsyncSession = Depends(get_db)):
    """Create a new tag."""
    # Check if tag name already exists
    existing = await db.execute(select(Tag).where(Tag.name == data.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Tag name already exists")
    tag = Tag(name=data.name, color=data.color)
    db.add(tag)
    await db.flush()
    await db.refresh(tag)
    t = TagOut.model_validate(tag)
    t.article_count = 0
    return t


@router.put("/{tag_id}", response_model=TagOut)
async def update_tag(tag_id: int, data: TagUpdate, db: AsyncSession = Depends(get_db)):
    """Update a tag."""
    tag = await db.get(Tag, tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    if data.name is not None:
        tag.name = data.name
    if data.color is not None:
        tag.color = data.color
    await db.flush()
    await db.refresh(tag)
    return TagOut.model_validate(tag)


@router.delete("/{tag_id}")
async def delete_tag(tag_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a tag."""
    tag = await db.get(Tag, tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    await db.delete(tag)
    await db.flush()
    return {"message": "Tag deleted"}


# ─── Article Tags ───

@router.post("/articles/{article_id}/tags", response_model=list[TagOut])
async def set_article_tags(
    article_id: int, data: ArticleTagsUpdate, db: AsyncSession = Depends(get_db)
):
    """Set tags for an article."""
    article = await db.get(Article, article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    # Remove existing tags
    await db.execute(
        ArticleTag.__table__.delete().where(ArticleTag.article_id == article_id)
    )

    # Add new tags
    for tag_id in data.tag_ids:
        tag = await db.get(Tag, tag_id)
        if tag:
            db.add(ArticleTag(article_id=article_id, tag_id=tag_id))

    await db.flush()

    # Return updated tags
    result = await db.execute(
        select(Tag).join(ArticleTag).where(ArticleTag.article_id == article_id)
    )
    tags = result.scalars().all()
    return [TagOut.model_validate(t) for t in tags]

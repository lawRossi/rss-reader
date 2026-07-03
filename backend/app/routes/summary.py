"""Summary API routes - supports SSE streaming."""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.database import get_db
from app.models import Article
from app.services.summarizer import generate_summary, save_summary

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/articles", tags=["Summary"])


@router.get("/{article_id}/summary")
async def get_summary(article_id: int, db: AsyncSession = Depends(get_db)):
    """Get cached summary for an article."""
    article = await db.get(Article, article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    if not article.summary:
        raise HTTPException(status_code=404, detail="No summary available. Use POST to generate.")
    return {"summary": article.summary}


@router.post("/{article_id}/summary")
async def create_summary(
    article_id: int,
    force: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Generate summary for an article. Returns SSE stream.

    Args:
        force: If True, regenerate even if cached summary exists.
    """
    article = await db.get(Article, article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    # If summary exists and not forced, return cached
    if article.summary and not force:
        return {"summary": article.summary}

    # Clear cached summary when forcing regeneration
    if force:
        article.summary = ""
        await db.flush()

    # Generate streaming summary
    async def event_generator():
        collected = []
        had_error = False
        try:
            gen = await generate_summary(db, article, stream=True)
            async for chunk in gen:
                collected.append(chunk)
                yield {
                    "event": "chunk",
                    "data": json.dumps({"chunk": chunk}, ensure_ascii=False),
                }
        except RuntimeError as e:
            # LLM API error — don't save, just report
            had_error = True
            error_msg = str(e)
            logger.error(f"Summary generation error: {error_msg}")
            yield {
                "event": "error",
                "data": json.dumps({"error": error_msg}, ensure_ascii=False),
            }
        except Exception as e:
            had_error = True
            logger.error(f"Summary generation unexpected error: {e}")
            yield {
                "event": "error",
                "data": json.dumps({"error": f"生成失败: {str(e)}"}, ensure_ascii=False),
            }
        else:
            # Only save if no error occurred
            if collected:
                full_summary = "".join(collected)
                article.summary = full_summary
                await db.flush()
                yield {
                    "event": "done",
                    "data": json.dumps({"summary": full_summary}, ensure_ascii=False),
                }

    return EventSourceResponse(event_generator())

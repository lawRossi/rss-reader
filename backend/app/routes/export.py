"""Export API routes - Markdown and PDF."""

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Article, DailyBriefing, Feed
from app.services.exporter import export_articles_markdown, markdown_to_pdf

router = APIRouter(prefix="/api", tags=["Export"])


@router.get("/articles/export")
async def export_articles(
    format: str = Query("markdown", pattern="^(markdown|pdf)$"),
    article_ids: str = Query(None, description="Comma-separated article IDs"),
    db: AsyncSession = Depends(get_db),
):
    """Export articles in markdown or PDF format."""
    if article_ids:
        ids = [int(i) for i in article_ids.split(",")]
        result = await db.execute(
            select(Article)
            .options(selectinload(Article.feed))
            .where(Article.id.in_(ids))
        )
    else:
        result = await db.execute(
            select(Article)
            .options(selectinload(Article.feed))
            .order_by(Article.published_at.desc()).limit(50)
        )
    articles = result.scalars().unique().all()

    if not articles:
        raise HTTPException(status_code=404, detail="No articles found")

    md_content = export_articles_markdown(articles)

    if format == "pdf":
        # Generate PDF
        tmp_file = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        success = markdown_to_pdf(md_content, tmp_file.name)
        if not success:
            raise HTTPException(status_code=500, detail="PDF generation failed")
        return FileResponse(
            tmp_file.name,
            media_type="application/pdf",
            filename=f"rss-export-{len(articles)}-articles.pdf",
        )
    else:
        return FileResponse(
            _create_temp_md_file(md_content, "articles"),
            media_type="text/markdown",
            filename=f"rss-export-{len(articles)}-articles.md",
        )


@router.get("/daily-briefings/{briefing_id}/export")
async def export_briefing(
    briefing_id: int,
    format: str = Query("markdown", pattern="^(markdown|pdf|text)$"),
    db: AsyncSession = Depends(get_db),
):
    """Export a daily briefing."""
    briefing = await db.get(DailyBriefing, briefing_id)
    if not briefing:
        raise HTTPException(status_code=404, detail="Briefing not found")

    if format == "text":
        return FileResponse(
            _create_temp_text_file(briefing.script_text, f"briefing-{briefing.date}"),
            media_type="text/plain",
            filename=f"briefing-{briefing.date}.txt",
        )
    else:
        md = f"# {briefing.title}\n\n"
        md += f"**Date**: {briefing.date}\n\n"
        md += "---\n\n"
        md += briefing.script_text.replace("[S1]", "\n\n**🎤 主播一**: ").replace("[S2]", "\n\n**🎤 主播二**: ")
        md += "\n"

        if format == "pdf":
            tmp_file = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            success = markdown_to_pdf(md, tmp_file.name)
            if not success:
                raise HTTPException(status_code=500, detail="PDF generation failed")
            return FileResponse(
                tmp_file.name,
                media_type="application/pdf",
                filename=f"briefing-{briefing.date}.pdf",
            )
        else:
            return FileResponse(
                _create_temp_md_file(md, f"briefing-{briefing.date}"),
                media_type="text/markdown",
                filename=f"briefing-{briefing.date}.md",
            )


def _create_temp_md_file(content: str, prefix: str) -> str:
    """Create a temporary markdown file and return its path."""
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".md", prefix=prefix, delete=False)
    tmp.write(content)
    tmp.close()
    return tmp.name


def _create_temp_text_file(content: str, prefix: str) -> str:
    """Create a temporary text file and return its path."""
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", prefix=prefix, delete=False)
    tmp.write(content)
    tmp.close()
    return tmp.name

"""Article summarization service using LLM."""

import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Article
from app.services.llm_service import chat_completion

logger = logging.getLogger(__name__)

SUMMARY_PROMPT = """你是一个专业的新闻摘要助手。请用中文为以下文章生成一个简洁的摘要（200-300字），要求：
1. 提取文章的核心观点和关键信息
2. 语言简洁明了，避免冗余
3. 保持客观中立，不添加个人评价

文章标题：{title}
文章内容：{content}

请生成摘要："""


async def generate_summary(
    db: AsyncSession,
    article: Article,
    stream: bool = False,
) -> dict | AsyncGenerator[str, None]:
    """Generate summary for an article using LLM.

    Args:
        db: Database session
        article: Article model instance
        stream: Whether to use SSE streaming

    Returns:
        If stream=False: {"summary": "..."}
        If stream=True: async generator yielding content chunks
    """
    # Truncate content to avoid token limits
    content = article.content or ""
    if len(content) > 8000:
        content = content[:8000] + "..."

    # Build prompt
    prompt = SUMMARY_PROMPT.format(title=article.title, content=content)

    messages = [
        {"role": "system", "content": "你是一个专业的新闻摘要助手。"},
        {"role": "user", "content": prompt},
    ]

    result = await chat_completion(db, messages, stream=stream, config_context="summary")

    if stream:
        return result  # It's an async generator (errors propagated as RuntimeError)

    # Non-streaming: save and return
    if isinstance(result, dict):
        summary = result.get("content", "")
        if summary:
            article.summary = summary
            await db.flush()
        return {"summary": summary}
    return {"summary": ""}


async def save_summary(db: AsyncSession, article: Article, summary: str):
    """Save summary to article."""
    if summary:
        article.summary = summary
        await db.flush()

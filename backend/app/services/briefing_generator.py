"""Daily briefing generation service — creates single-narration news scripts.

Only generates NARRATION_PROMPT style (no [S1]/[S2] markers).
Dual-speaker dialogue (moss-ttsd) was removed in simplification.
"""

import json
import logging
import re
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select, desc
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Article, DailyBriefing, Feed
from app.services.llm_service import chat_completion

logger = logging.getLogger(__name__)

# ─── Local timezone detection ───

try:
    import time as _time
    _offset = -_time.timezone  # seconds east of UTC
    _hours = _offset // 3600
    _mins = (_offset % 3600) // 60
    if _hours == 8 and _mins == 0:
        LOCAL_TZ = ZoneInfo("Asia/Shanghai")
    elif _hours == 9 and _mins == 0:
        LOCAL_TZ = ZoneInfo("Asia/Tokyo")
    elif _hours == 7 and _mins == 0:
        LOCAL_TZ = ZoneInfo("Asia/Bangkok")
    elif _hours == 5 and _mins == 30:
        LOCAL_TZ = ZoneInfo("Asia/Kolkata")
    elif _hours == 0 and _mins == 0:
        LOCAL_TZ = ZoneInfo("UTC")
    elif _hours == -5 and _mins == 0:
        LOCAL_TZ = ZoneInfo("America/New_York")
    elif _hours == -8 and _mins == 0:
        LOCAL_TZ = ZoneInfo("America/Los_Angeles")
    else:
        LOCAL_TZ = ZoneInfo("Asia/Shanghai")
except Exception:
    LOCAL_TZ = ZoneInfo("Asia/Shanghai")

logger.info(f"Briefing generator using timezone: {LOCAL_TZ}")

# ─── Article preprocessing ───

MAX_ARTICLES = 30          # max articles to include in a briefing
MAX_PER_FEED = 5           # max articles from the same feed
MAX_CONTENT_LEN = 5000     # truncate article content beyond this
TITLE_SIM_THRESHOLD = 0.40   # Jaccard threshold for title dedup
CONTENT_SIM_THRESHOLD = 0.50  # Jaccard threshold for content dedup


def _char_bigrams(text: str) -> set[str]:
    """Character bigrams for Chinese text similarity.

    Strips non-Chinese, non-alphanumeric characters first so that
    punctuation differences don't inflate the bigram set.
    """
    if not text:
        return set()
    # Keep only Chinese chars and ASCII alphanumeric
    clean = re.sub(r'[^\u4e00-\u9fff\w]', '', text.lower())
    return set(clean[i:i+2] for i in range(len(clean) - 1))


def _word_tokens(text: str) -> set[str]:
    """Extract word tokens (Chinese chars + alphanumeric)."""
    if not text:
        return set()
    return set(re.findall(r'[\u4e00-\u9fff\w]+', text.lower()))


def _jaccard(a: set, b: set) -> float:
    """Jaccard similarity between two sets."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _title_similar(t1: str, t2: str) -> bool:
    """Check if two titles are near-duplicates using character bigrams."""
    return _jaccard(_char_bigrams(t1), _char_bigrams(t2)) >= TITLE_SIM_THRESHOLD


def _content_similar(c1: str, c2: str) -> bool:
    """Check if two content bodies are near-duplicates using character bigrams."""
    return _jaccard(_char_bigrams(c1), _char_bigrams(c2)) >= CONTENT_SIM_THRESHOLD


def _preprocess_articles(articles: list) -> list:
    """Filter, deduplicate and sort articles for briefing diversity.

    1. Truncate content > MAX_CONTENT_LEN
    2. Sort by content length (longer first — more substantial)
    3. Source diversity: at most MAX_PER_FEED per feed
    4. Title dedup: remove near-duplicate titles
    5. Content dedup: remove near-duplicate content
    6. Keep top MAX_ARTICLES
    """
    if not articles:
        return []

    # 1. Truncate long content
    for a in articles:
        if a.content and len(a.content) > MAX_CONTENT_LEN:
            a.content = a.content[:MAX_CONTENT_LEN]

    # 2. Sort by content length descending (most substantial first)
    articles.sort(key=lambda a: len(a.content or ""), reverse=True)

    # 3. Source diversity
    feed_count: dict[int, int] = {}
    diverse = []
    for a in articles:
        cnt = feed_count.get(a.feed_id, 0)
        if cnt >= MAX_PER_FEED:
            continue
        feed_count[a.feed_id] = cnt + 1
        diverse.append(a)

    # 4. Title dedup
    title_deduped = []
    for a in diverse:
        if not any(_title_similar(a.title, existing.title) for existing in title_deduped):
            title_deduped.append(a)

    # 5. Content dedup (only if both have content)
    final = []
    for a in title_deduped:
        if not a.content:
            final.append(a)
        elif not any(
            existing.content and _content_similar(a.content, existing.content)
            for existing in final
        ):
            final.append(a)

    # 6. Limit
    return final[:MAX_ARTICLES]


# ─── Narration prompt (single speaker, no markers) ───

NARRATION_PROMPT = """你是一个专业的新闻播报员。请根据以下新闻文章列表，生成一段单人播报式日报。

要求：
1. 以专业新闻播报员的口吻，单人连贯播报
2. 按重要性排序新闻
3. 每篇新闻用 2-3 句话概括核心内容
4. 不要使用任何说话人标记（如 [S1]、[S2] 等）
5. 语言自然流畅，适合语音朗读
6. 开头要有问候语，结尾要有结束语
7. 整体时长控制在 3-5 分钟

新闻列表：
{articles}

请生成播报脚本："""


async def generate_briefing(
    db: AsyncSession,
    date_str: str | None = None,
    time_range: str = "today",
    group_id: int | None = None,
    ref_audio_id: str | None = None,
    tts_edge_voice: str | None = None,
) -> DailyBriefing | None:
    """Generate a daily briefing based on recent articles.

    Returns the generated DailyBriefing, or None if there are no articles
    matching the criteria (no news to report).

    Args:
        db: Database session
        date_str: Date string in YYYY-MM-DD format
        time_range: Time range filter — "today" (since midnight UTC),
                    "12h" (last 12 hours), "24h" (last 24 hours)
        group_id: Filter by feed group ID; None means all groups
        ref_audio_id: Override reference audio ID; None = use global config default
        tts_edge_voice: Override Edge TTS voice; None = use global config default
    """
    # Use local timezone for date_str and "today" boundary
    now_local = datetime.now(LOCAL_TZ)
    now_utc = datetime.now(timezone.utc)

    if date_str is None:
        date_str = now_local.strftime("%Y-%m-%d")

    # Calculate time range in UTC for DB query (published_at is stored in UTC)
    if time_range == "today":
        # Local midnight → convert to UTC for comparison
        local_midnight = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        since = local_midnight.astimezone(timezone.utc)
    elif time_range == "12h":
        since = now_utc - timedelta(hours=12)
    else:  # "24h" (default fallback)
        since = now_utc - timedelta(hours=24)

    # Build article query with optional group filter
    query = (
        select(Article)
        .options(selectinload(Article.feed))
    )

    if group_id is not None:
        query = query.join(Article.feed).where(Feed.group_id == group_id)

    query = (
        query
        .where(Article.published_at >= since)
        .order_by(desc(Article.published_at))
        .limit(100)  # fetch more for preprocessing/dedup
    )

    # Fetch articles
    result = await db.execute(query)
    articles = result.scalars().unique().all()

    if not articles:
        logger.info(f"No articles found for date={date_str}, time_range={time_range}, group_id={group_id}")
        return None

    # Preprocess: dedup, source diversity, length-based selection
    articles = _preprocess_articles(articles)
    logger.info(
        f"After preprocessing: {len(articles)} articles selected "
        f"(date={date_str}, time_range={time_range}, group_id={group_id})"
    )

    # Build articles summary for LLM
    articles_text = ""
    article_list = []
    for i, article in enumerate(articles, 1):
        # Truncate content
        content = (article.content or "")[:500]
        articles_text += f"\n{i}. 标题: {article.title}\n"
        articles_text += f"   来源: {article.feed.title if article.feed else 'Unknown'}\n"
        articles_text += f"   内容概要: {content}\n"
        article_list.append({
            "id": article.id,
            "title": article.title,
            "url": article.url,
        })

    # Build a descriptive title
    time_labels = {"today": "当日", "12h": "近12h", "24h": "近24h"}
    time_label = time_labels.get(time_range, time_range)
    title = f"{date_str} 播报 · {len(articles)}篇 · {time_label}"

    # Append group name if filtering by a specific group
    if group_id is not None:
        from app.models import Group
        group = await db.get(Group, group_id)
        if group:
            title = f"{date_str} {group.name} · {len(articles)}篇 · {time_label}"

    # Create briefing record
    briefing = DailyBriefing(
        date=date_str,
        title=title,
        content_json=json.dumps(article_list, ensure_ascii=False),
        status="generating",
        ref_audio_id=ref_audio_id,
        tts_edge_voice=tts_edge_voice,
    )
    db.add(briefing)
    await db.flush()
    await db.refresh(briefing)

    # Use single-speaker narration prompt (no [S1]/[S2] markers)
    prompt = NARRATION_PROMPT.format(articles=articles_text)

    system_content = "你是一个专业的新闻播报员，擅长将新闻整理成生动的播报脚本。"

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": prompt},
    ]

    try:
        result = await chat_completion(db, messages, stream=False, config_context="briefing")
        script = result.get("content", "")

        # Check for any error patterns
        error_prefixes = ("API 调用失败", "请求失败", "LLM API key not configured", "not configured")
        if script.startswith(error_prefixes):
            briefing.status = "failed"
            briefing.script_text = script
            logger.warning(f"Briefing generation failed: {script[:100]}")
        else:
            # Strip any stray speaker markers
            script = script.replace("[S1]", "").replace("[S2]", "").strip()
            briefing.script_text = script
            briefing.status = "completed"

    except Exception as e:
        logger.error(f"Briefing generation failed: {e}")
        briefing.status = "failed"
        briefing.script_text = f"生成失败: {str(e)}"

    await db.flush()
    await db.refresh(briefing)
    return briefing

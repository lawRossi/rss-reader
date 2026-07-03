"""Article content fetching from original URL service."""

import logging
import re
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

# Minimum visible text length (after stripping HTML) to consider content valid
MIN_VISIBLE_TEXT_LENGTH = 100
# Minimum raw HTML length to consider content valid
MIN_RAW_HTML_LENGTH = 300


def _resolve_url(base: str, path: str) -> str:
    """Resolve relative URL to absolute."""
    return urljoin(base, path)


def _get_visible_text_length(html: str) -> int:
    """Get the length of visible text content, stripping HTML tags."""
    text = re.sub(r"<[^>]+>", "", html)
    text = re.sub(r"\s+", " ", text).strip()
    return len(text)


async def fetch_full_content(url: str) -> str | None:
    """Fetch full article content from original URL.

    Uses readability-like heuristics to extract the main article content.

    Returns HTML string if successful and content is substantial enough,
    or None on failure / insufficient content.
    """
    try:
        import httpx
        from bs4 import BeautifulSoup

        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; RSSReader/1.0)"},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "lxml")

        # Remove unwanted elements
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "iframe"]):
            tag.decompose()

        content = None

        # Try common article containers (ordered by specificity)
        for selector in [
            "article",
            "[role=main]",
            ".post-content",
            ".entry-content",
            ".article-content",
            ".article-body",
            "#content",
            ".content",
            "main",
        ]:
            container = soup.select_one(selector)
            if container:
                # Resolve relative image URLs
                for img in container.find_all("img"):
                    src = img.get("src") or ""
                    if src and not src.startswith(("http://", "https://", "data:")):
                        img["src"] = _resolve_url(url, src)
                # Resolve relative link URLs
                for a_tag in container.find_all("a"):
                    href = a_tag.get("href") or ""
                    if href and not href.startswith(("http://", "https://", "mailto:", "#", "javascript:")):
                        a_tag["href"] = _resolve_url(url, href)
                content = str(container)
                break

        # Fallback: return body content (excluding script/style)
        if content is None:
            body = soup.find("body")
            if body:
                content = str(body)

        # Quality check: reject if content is too thin
        if content is not None:
            visible_len = _get_visible_text_length(content)
            if visible_len < MIN_VISIBLE_TEXT_LENGTH or len(content) < MIN_RAW_HTML_LENGTH:
                logger.debug(
                    f"Fetched content too thin from {url}: "
                    f"visible={visible_len}, html={len(content)}"
                )
                return None

        return content

    except httpx.TimeoutException:
        logger.warning(f"Timeout fetching content from {url}")
        return None
    except httpx.HTTPStatusError as e:
        logger.warning(f"HTTP error {e.response.status_code} fetching {url}")
        return None
    except Exception as e:
        logger.debug(f"Failed to fetch full content from {url}: {e}")
        return None

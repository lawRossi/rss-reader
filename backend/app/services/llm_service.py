"""LLM API calling service - supports OpenAI-compatible interfaces."""

import asyncio
import json
import logging
import random
from typing import AsyncGenerator

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Setting

logger = logging.getLogger(__name__)

# Supported LLM config contexts (for independent per-feature configs)
LLM_CONTEXTS = ["summary", "briefing"]

# Retry configuration for 429 Too Many Requests
MAX_RETRIES = 3
BASE_RETRY_DELAY = 2.0  # seconds


async def _retry_delay(attempt: int, resp: httpx.Response | None = None):
    """Calculate and sleep for exponential backoff delay with jitter.

    Respects the Retry-After header if present.
    """
    delay = BASE_RETRY_DELAY * (2 ** attempt) + random.uniform(0, 1)
    if resp is not None:
        retry_after = resp.headers.get("retry-after")
        if retry_after:
            try:
                delay = float(retry_after)
            except ValueError:
                pass
    logger.warning(f"Rate limited (429), retrying in {delay:.1f}s (attempt {attempt + 1}/{MAX_RETRIES})")
    await asyncio.sleep(delay)


async def get_llm_config(db: AsyncSession, context: str = "") -> dict:
    """Read LLM configuration from settings table.

    Supports per-feature config with fallback to global 'llm_*' settings.
    For example, context="summary" looks for 'summary_api_endpoint',
    'summary_api_key', etc., falling back to 'llm_api_endpoint', 'llm_api_key'.

    Args:
        db: Database session
        context: Config context — "summary", "briefing", or "" for global default
    """
    result = await db.execute(select(Setting))
    settings = {s.key: s.value for s in result.scalars().all()}

    prefix = f"{context}_" if context else ""
    fallback_prefix = "llm_"

    def _get(key: str, default: str = "") -> str:
        # Try context-specific key first, then fall back to llm_ prefix
        val = settings.get(f"{prefix}{key}") or settings.get(f"{fallback_prefix}{key}")
        return val if val is not None else default

    endpoint = _get("api_endpoint", "https://api.openai.com/v1").rstrip("/")
    api_key = _get("api_key", "")
    model = _get("model_name", "gpt-3.5-turbo")

    raw_max_tokens = _get("max_tokens", "1024")
    raw_temperature = _get("temperature", "0.7")

    try:
        max_tokens = int(raw_max_tokens)
    except (ValueError, TypeError):
        max_tokens = 1024

    try:
        temperature = float(raw_temperature)
    except (ValueError, TypeError):
        temperature = 0.7

    return {
        "api_endpoint": endpoint,
        "api_key": api_key,
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }


async def chat_completion(
    db: AsyncSession,
    messages: list[dict],
    stream: bool = False,
    config_context: str = "",
) -> dict | AsyncGenerator[str, None]:
    """Call LLM chat completion API.

    Args:
        db: Database session for reading config
        messages: List of message dicts
        stream: Whether to use SSE streaming
        config_context: Config context for per-feature LLM settings.
                        "summary", "briefing", or "" for global default.

    Returns:
        If stream=False: dict with "content" key
        If stream=True: async generator yielding content chunks
    """
    config = await get_llm_config(db, context=config_context)
    api_key = config["api_key"]

    if not api_key:
        error_msg = "API 调用失败: LLM API key 未配置，请前往设置页面配置。"
        if stream:
            async def error_gen():
                raise RuntimeError(error_msg)
            return error_gen()
        return {"content": error_msg}

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": config["model"],
        "messages": messages,
        "max_tokens": config["max_tokens"],
        "temperature": config["temperature"],
        "stream": stream,
    }

    url = f"{config['api_endpoint']}/chat/completions"

    try:
        if stream:
            # Return a generator that manages its own client lifecycle
            return _stream_response(url, headers, payload)
        else:
            # Non-streaming: retry on 429
            for attempt in range(MAX_RETRIES):
                try:
                    async with httpx.AsyncClient(timeout=120.0) as client:
                        resp = await client.post(url, headers=headers, json=payload)
                        resp.raise_for_status()
                        data = resp.json()
                        content = data["choices"][0]["message"]["content"]
                        return {"content": content}
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429 and attempt < MAX_RETRIES - 1:
                        await _retry_delay(attempt, e.response)
                        continue
                    raise

    except httpx.HTTPStatusError as e:
        error_detail = f"HTTP {e.response.status_code}"
        try:
            err_data = e.response.json()
            error_detail = err_data.get("error", {}).get("message", error_detail)
        except Exception:
            pass
        logger.error(f"LLM API error: {error_detail}")
        if stream:
            async def error_gen():
                raise RuntimeError(f"API 调用失败: {error_detail}")
            return error_gen()
        return {"content": f"API 调用失败: {error_detail}"}

    except Exception as e:
        logger.error(f"LLM API call failed: {e}")
        if stream:
            async def error_gen():
                raise RuntimeError(f"请求失败: {str(e)}")
            return error_gen()
        return {"content": f"请求失败: {str(e)}"}


async def _stream_response(
    url: str,
    headers: dict,
    payload: dict,
) -> AsyncGenerator[str, None]:
    """Handle SSE streaming response.

    Manages its own httpx client lifecycle — the client is created inside
    the generator and lives only as long as the stream iteration.
    Automatically retries on 429 (rate limit) with exponential backoff.
    """
    for attempt in range(MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream("POST", url, headers=headers, json=payload) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                data = json.loads(data_str)
                                if choices := data.get("choices", []):
                                    delta = choices[0].get("delta", {})
                                    if content := delta.get("content", ""):
                                        yield content
                            except json.JSONDecodeError:
                                continue
            # Success — exit retry loop
            return
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429 and attempt < MAX_RETRIES - 1:
                await _retry_delay(attempt, e.response)
                continue
            error_detail = f"HTTP {e.response.status_code}"
            try:
                err_data = e.response.json()
                error_detail = err_data.get("error", {}).get("message", error_detail)
            except Exception:
                pass
            raise RuntimeError(f"API 调用失败: {error_detail}")
        except Exception as e:
            raise RuntimeError(f"请求失败: {str(e)}")

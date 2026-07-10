"""Pydantic schemas for API request/response validation."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel


# ─── Setting ───
class SettingOut(BaseModel):
    key: str
    value: str

    model_config = {"from_attributes": True}


class SettingsUpdate(BaseModel):
    settings: dict[str, str]


class TtsEngineOption(BaseModel):
    label: str
    description: str


class TtsEngineOptions(BaseModel):
    engines: dict[str, TtsEngineOption]


# ─── Group ───
class GroupCreate(BaseModel):
    name: str
    sort_order: int = 0


class GroupUpdate(BaseModel):
    name: Optional[str] = None
    sort_order: Optional[int] = None


class GroupOut(BaseModel):
    id: int
    name: str
    sort_order: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Feed ───
class FeedCreate(BaseModel):
    url: str
    group_id: Optional[int] = None


class FeedUpdate(BaseModel):
    title: Optional[str] = None
    url: Optional[str] = None
    group_id: Optional[int] = None


class FeedOut(BaseModel):
    id: int
    group_id: Optional[int] = None
    title: str
    url: str
    site_url: str
    description: str
    icon: str
    last_fetched_at: Optional[datetime] = None
    created_at: datetime
    group_name: Optional[str] = None
    article_count: Optional[int] = None

    model_config = {"from_attributes": True}


# ─── Article ───
class ArticleOut(BaseModel):
    id: int
    feed_id: int
    guid: str
    title: str
    url: str
    author: str
    content: str
    summary: str
    content_type: str
    is_read: bool
    is_starred: bool
    published_at: Optional[datetime] = None
    fetched_at: datetime
    created_at: datetime
    feed_title: Optional[str] = None
    tags: list = []

    model_config = {"from_attributes": True}


class ArticleListItem(BaseModel):
    id: int
    feed_id: int
    title: str
    url: str
    author: str
    summary: str
    is_read: bool
    is_starred: bool
    published_at: Optional[datetime] = None
    fetched_at: datetime
    feed_title: Optional[str] = None
    feed_icon: Optional[str] = None
    tags: list = []

    model_config = {"from_attributes": True}


class ArticleUpdate(BaseModel):
    is_read: Optional[bool] = None
    is_starred: Optional[bool] = None


class BatchAction(BaseModel):
    article_ids: list[int]
    action: str  # "mark_read", "mark_unread", "star", "unstar"
    value: Optional[bool] = None


class PaginatedResponse(BaseModel):
    items: list
    total: int
    page: int
    page_size: int
    total_pages: int


# ─── Tag ───
class TagCreate(BaseModel):
    name: str
    color: str = "#3B82F6"


class TagUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None


class TagOut(BaseModel):
    id: int
    name: str
    color: str
    created_at: datetime
    article_count: Optional[int] = None

    model_config = {"from_attributes": True}


class ArticleTagsUpdate(BaseModel):
    tag_ids: list[int]


# ─── Daily Briefing ───
class DailyBriefingOut(BaseModel):
    id: int
    date: str
    title: str
    content_json: str
    script_text: str
    audio_path: Optional[str] = None
    status: str
    ref_audio_id: Optional[str] = None
    tts_edge_voice: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DailyBriefingGenerate(BaseModel):
    date: Optional[str] = None  # YYYY-MM-DD, defaults to today
    time_range: str = "today"   # "today", "12h", "24h"
    group_id: Optional[int] = None  # None = all groups
    ref_audio_id: Optional[str] = None  # Override reference audio; None = use global
    tts_edge_voice: Optional[str] = None  # Override Edge TTS voice; None = use global


# ─── Scheduled Task ───
class ScheduledTaskCreate(BaseModel):
    name: str
    cron_expr: str  # e.g. "0 8 * * *" = daily at 08:00
    time_range: str = "today"  # "today", "12h", "24h"
    group_id: Optional[int] = None
    include_audio: bool = True
    ref_audio_id: Optional[str] = None  # Override reference audio; None = use global
    tts_edge_voice: Optional[str] = None  # Override Edge TTS voice; None = use global


class ScheduledTaskUpdate(BaseModel):
    name: Optional[str] = None
    cron_expr: Optional[str] = None
    time_range: Optional[str] = None
    group_id: Optional[int] = None
    include_audio: Optional[bool] = None
    ref_audio_id: Optional[str] = None
    tts_edge_voice: Optional[str] = None
    enabled: Optional[bool] = None


class ScheduledTaskOut(BaseModel):
    id: int
    name: str
    cron_expr: str
    time_range: str
    group_id: Optional[int] = None
    include_audio: bool
    ref_audio_id: Optional[str] = None
    tts_edge_voice: Optional[str] = None
    enabled: bool
    last_run_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Export ───
class ExportParams(BaseModel):
    format: str = "markdown"  # markdown, pdf
    article_ids: Optional[list[int]] = None

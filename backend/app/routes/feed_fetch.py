"""Feed fetch status and manual trigger API routes."""

import logging

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models import Feed, Setting
from app.services.feed_fetcher import fetch_all_feeds
from app.services.task_scheduler import scheduler

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/feeds", tags=["Feeds"])


@router.get("/fetch-status")
async def get_fetch_status(db: AsyncSession = Depends(get_db)):
    """Get the current feed fetch job status.

    Returns:
        interval_minutes: Current fetch interval in minutes.
        next_run: ISO format timestamp of next scheduled fetch, or null.
        last_run: ISO format timestamp of the most recent fetch across all feeds, or null.
    """
    # Get job status from scheduler
    job_status = scheduler.get_fetch_job_status()

    # Get the most recent fetch time from any feed
    result = await db.execute(
        select(func.max(Feed.last_fetched_at))
    )
    last_run = result.scalar_one_or_none()

    return {
        "interval_minutes": job_status.get("interval_minutes"),
        "next_run": job_status.get("next_run"),
        "last_run": last_run.isoformat() if last_run else None,
    }


@router.post("/fetch-now")
async def trigger_fetch_now(background_tasks: BackgroundTasks):
    """Manually trigger a full feed fetch in the background."""
    background_tasks.add_task(fetch_all_feeds)
    logger.info("Manual feed fetch triggered via API")
    return {"message": "抓取已触发，正在后台运行"}

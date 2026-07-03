"""APScheduler-based task scheduler for automatic daily briefing generation."""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from app.database import async_session
from app.models import ScheduledTask, Setting

logger = logging.getLogger(__name__)


def _get_local_timezone() -> str:
    """Detect the system's local timezone as an IANA timezone string.

    Falls back to 'Asia/Shanghai' if detection fails.
    """
    try:
        # Get local UTC offset in seconds (negative for east of UTC)
        # time.timezone gives the offset west of UTC in seconds
        import time as _time
        offset_seconds = -_time.timezone  # positive for east of UTC
        hours = offset_seconds // 3600
        minutes = (offset_seconds % 3600) // 60

        # Common IANA timezone mapping based on offset
        common_zones = {
            (8, 0): "Asia/Shanghai",
            (7, 0): "Asia/Bangkok",
            (9, 0): "Asia/Tokyo",
            (5, 30): "Asia/Kolkata",
            (0, 0): "UTC",
            (-5, 0): "America/New_York",
            (-8, 0): "America/Los_Angeles",
        }
        key = (hours, minutes)
        if key in common_zones:
            return common_zones[key]

        # Fallback: try to resolve via zoneinfo
        now = datetime.now(timezone.utc).astimezone()
        tz_name = now.tzinfo.tzname(now) if now.tzinfo else "UTC"
        return tz_name or "UTC"
    except Exception:
        return "Asia/Shanghai"


# Detect local timezone once at module load
LOCAL_TZ = _get_local_timezone()
logger.info(f"Detected local timezone: {LOCAL_TZ}")


class TaskScheduler:
    """Manages scheduled briefing tasks via APScheduler.

    At startup, loads all enabled tasks from the database and registers them
    as APScheduler jobs. Supports dynamic add/update/remove of jobs when
    tasks are created/modified/deleted via the API.
    """

    def __init__(self):
        self.scheduler = AsyncIOScheduler(timezone=LOCAL_TZ)
        self._locks: dict[int, asyncio.Lock] = {}

    async def start(self):
        """Start the scheduler and load all enabled tasks from DB."""
        self.scheduler.start()
        async with async_session() as db:
            result = await db.execute(
                select(ScheduledTask).where(ScheduledTask.enabled == True)
            )
            tasks = result.scalars().all()
            for task in tasks:
                self._add_job(task)
            logger.info(f"Scheduler started with {len(tasks)} active task(s)")

    async def stop(self):
        """Stop the scheduler gracefully."""
        self.scheduler.shutdown(wait=True)
        logger.info("Scheduler stopped")

    # ── Internal job management ──

    @staticmethod
    def _get_job_id(task_id: int) -> str:
        return f"briefing_task_{task_id}"

    def _add_job(self, task: ScheduledTask):
        """Register an APScheduler job for a task."""
        job_id = self._get_job_id(task.id)
        trigger = CronTrigger.from_crontab(task.cron_expr)
        self.scheduler.add_job(
            self._execute_job,
            trigger=trigger,
            id=job_id,
            args=[task.id],
            name=task.name,
            misfire_grace_time=600,  # 10 minutes grace for missed triggers
            coalesce=True,           # Only run once if multiple firings were missed
            replace_existing=True,
        )
        logger.info(f"Job registered: '{task.name}' (id={job_id}, cron='{task.cron_expr}')")

    def _remove_job(self, task_id: int):
        """Remove an APScheduler job by task ID."""
        job_id = self._get_job_id(task_id)
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
            logger.info(f"Job removed: {job_id}")

    # ── Public API for route handlers ──

    async def add_task(self, task: ScheduledTask):
        """Add a task to the scheduler (only if enabled)."""
        if task.enabled:
            self._add_job(task)

    async def update_task(self, task: ScheduledTask):
        """Update a task in the scheduler (remove old, add new if enabled)."""
        self._remove_job(task.id)
        if task.enabled:
            self._add_job(task)

    async def remove_task(self, task_id: int):
        """Remove a task from the scheduler."""
        self._remove_job(task_id)

    async def execute_task(self, task_id: int) -> int | None:
        """Execute a task immediately (manual trigger).

        Returns the generated briefing ID on success.
        Returns None if there were no articles to generate (not an error).
        Raises on actual execution failures.
        Uses a per-task lock to prevent concurrent executions.
        """
        if task_id not in self._locks:
            self._locks[task_id] = asyncio.Lock()

        async with self._locks[task_id]:
            async with async_session() as db:
                try:
                    task = await db.get(ScheduledTask, task_id)
                    if not task:
                        logger.error(f"ScheduledTask {task_id} not found")
                        return None

                    # Read TTS engine setting
                    result = await db.execute(
                        select(Setting).where(Setting.key == "tts_engine")
                    )
                    tts_setting = result.scalar_one_or_none()
                    tts_engine = tts_setting.value if tts_setting else "moss-ttsd"

                    # Generate the briefing script
                    from app.services.briefing_generator import generate_briefing

                    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                    briefing = await generate_briefing(
                        db=db,
                        date_str=date_str,
                        time_range=task.time_range,
                        group_id=task.group_id,
                        tts_engine=tts_engine,
                    )

                    if briefing is None:
                        logger.info(
                            f"Task '{task.name}': no articles found, skipping."
                        )
                        # Still update last_run_at so we don't keep retrying
                        task.last_run_at = datetime.now(timezone.utc)
                        await db.commit()
                        return None  # None = no articles, not an error

                    # Update last_run_at
                    task.last_run_at = datetime.now(timezone.utc)

                    # Commit briefing + last_run_at BEFORE triggering audio,
                    # because generate_briefing_audio opens its own session
                    # and needs to read the committed briefing record.
                    await db.commit()

                    # Optionally generate audio (uses a separate session)
                    if task.include_audio and briefing.status == "completed" and briefing.script_text not in ("", "暂无新闻更新。"):
                        from app.services.tts_service import generate_briefing_audio

                        await generate_briefing_audio(briefing.id, ref_audio_id=task.ref_audio_id)
                        logger.info(f"Audio generation triggered for briefing {briefing.id}")

                    logger.info(
                        f"Task '{task.name}' executed, briefing id={briefing.id}, "
                        f"status={briefing.status}"
                    )
                    return briefing.id

                except Exception as e:
                    await db.rollback()
                    logger.error(f"Task execution failed (id={task_id}): {e}", exc_info=True)
                    raise  # Re-raise so caller can distinguish from "no articles"

    async def _execute_job(self, task_id: int):
        """APScheduler job callback — wraps execute_task with logging."""
        logger.info(f"⏰ Scheduled job triggered for task {task_id}")
        await self.execute_task(task_id)


# ── Singleton ──

scheduler = TaskScheduler()

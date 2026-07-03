"""Scheduled Task API routes — CRUD + manual trigger for briefing tasks."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import ScheduledTask
from app.schemas import (
    ScheduledTaskCreate,
    ScheduledTaskUpdate,
    ScheduledTaskOut,
)
from app.services.task_scheduler import scheduler

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/scheduled-tasks", tags=["Scheduled Tasks"])


@router.get("", response_model=list[ScheduledTaskOut])
async def list_tasks(db: AsyncSession = Depends(get_db)):
    """Get all scheduled tasks."""
    result = await db.execute(
        select(ScheduledTask).order_by(desc(ScheduledTask.created_at))
    )
    return result.scalars().all()


@router.post("", response_model=ScheduledTaskOut, status_code=201)
async def create_task(
    data: ScheduledTaskCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new scheduled task and register it with the scheduler."""
    task = ScheduledTask(
        name=data.name,
        cron_expr=data.cron_expr,
        time_range=data.time_range,
        group_id=data.group_id,
        include_audio=data.include_audio,
        enabled=True,
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)

    # Register with APScheduler
    await scheduler.add_task(task)

    logger.info(f"Scheduled task created: '{task.name}' (id={task.id})")
    return task


@router.get("/{task_id}", response_model=ScheduledTaskOut)
async def get_task(task_id: int, db: AsyncSession = Depends(get_db)):
    """Get a scheduled task by ID."""
    task = await db.get(ScheduledTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Scheduled task not found")
    return task


@router.put("/{task_id}", response_model=ScheduledTaskOut)
async def update_task(
    task_id: int,
    data: ScheduledTaskUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a scheduled task and sync with the scheduler."""
    task = await db.get(ScheduledTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Scheduled task not found")

    update_fields = data.model_dump(exclude_unset=True)
    for key, value in update_fields.items():
        setattr(task, key, value)

    await db.flush()
    await db.refresh(task)

    # Sync with APScheduler
    await scheduler.update_task(task)

    logger.info(f"Scheduled task updated: '{task.name}' (id={task.id})")
    return task


@router.delete("/{task_id}")
async def delete_task(task_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a scheduled task and remove it from the scheduler."""
    task = await db.get(ScheduledTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Scheduled task not found")

    await db.delete(task)
    await db.flush()

    # Remove from APScheduler
    await scheduler.remove_task(task_id)

    logger.info(f"Scheduled task deleted: id={task_id}")
    return {"message": "Scheduled task deleted"}


@router.post("/{task_id}/toggle", response_model=ScheduledTaskOut)
async def toggle_task(task_id: int, db: AsyncSession = Depends(get_db)):
    """Toggle a scheduled task's enabled/disabled state."""
    task = await db.get(ScheduledTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Scheduled task not found")

    task.enabled = not task.enabled
    await db.flush()
    await db.refresh(task)

    # Sync with APScheduler
    await scheduler.update_task(task)

    status = "enabled" if task.enabled else "disabled"
    logger.info(f"Scheduled task '{task.name}' {status}")
    return task


@router.post("/{task_id}/execute-now")
async def execute_task_now(
    task_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Execute a scheduled task immediately (manual trigger)."""
    task = await db.get(ScheduledTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Scheduled task not found")

    try:
        briefing_id = await scheduler.execute_task(task_id)
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Task execution failed — check server logs for details",
        )

    if briefing_id is None:
        return {"message": "所选时间范围内没有新文章，无需生成日报。", "briefing_id": None, "no_content": True}

    logger.info(f"Manual execution: task '{task.name}' → briefing #{briefing_id}")
    return {"message": "Task executed", "briefing_id": briefing_id}

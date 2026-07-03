"""Groups API routes."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete

from app.database import get_db
from app.models import Group, Feed
from app.schemas import GroupCreate, GroupUpdate, GroupOut

router = APIRouter(prefix="/api/groups", tags=["Groups"])


@router.get("", response_model=list[GroupOut])
async def list_groups(db: AsyncSession = Depends(get_db)):
    """List all groups."""
    result = await db.execute(select(Group).order_by(Group.sort_order, Group.name))
    return result.scalars().all()


@router.post("", response_model=GroupOut, status_code=201)
async def create_group(data: GroupCreate, db: AsyncSession = Depends(get_db)):
    """Create a new group."""
    group = Group(name=data.name, sort_order=data.sort_order)
    db.add(group)
    await db.flush()
    await db.refresh(group)
    return group


@router.put("/{group_id}", response_model=GroupOut)
async def update_group(group_id: int, data: GroupUpdate, db: AsyncSession = Depends(get_db)):
    """Update a group."""
    group = await db.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    if data.name is not None:
        group.name = data.name
    if data.sort_order is not None:
        group.sort_order = data.sort_order
    await db.flush()
    await db.refresh(group)
    return group


@router.delete("/{group_id}")
async def delete_group(group_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a group and unlink its feeds."""
    group = await db.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    # Unlink feeds from this group
    await db.execute(
        Feed.__table__.update().where(Feed.group_id == group_id).values(group_id=None)
    )
    await db.delete(group)
    await db.flush()
    return {"message": "Group deleted"}

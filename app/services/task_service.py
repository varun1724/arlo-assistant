"""Task, Goal, and Habit service — CRUD operations."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import user_today
from app.db.models import TaskRow, GoalRow, HabitRow


# ─── Tasks ──────────────────────────────────────────────

async def create_task(
    session: AsyncSession,
    title: str,
    description: Optional[str] = None,
    priority: str = "medium",
    due_date: Optional[date] = None,
    category: Optional[str] = None,
    recurring: Optional[str] = None,
    *,
    user_id: uuid.UUID,
) -> TaskRow:
    row = TaskRow(
        user_id=user_id,
        title=title,
        description=description,
        priority=priority,
        due_date=due_date,
        category=category,
        recurring=recurring,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def get_tasks(
    session: AsyncSession,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    category: Optional[str] = None,
    *,
    user_id: uuid.UUID,
) -> list[TaskRow]:
    q = select(TaskRow).where(TaskRow.user_id == user_id)
    if status:
        q = q.where(TaskRow.status == status)
    if priority:
        q = q.where(TaskRow.priority == priority)
    if category:
        q = q.where(TaskRow.category == category)
    q = q.order_by(TaskRow.created_at.desc())
    result = await session.execute(q)
    return list(result.scalars().all())


async def get_task(session: AsyncSession, task_id: uuid.UUID) -> Optional[TaskRow]:
    return await session.get(TaskRow, task_id)


async def update_task(
    session: AsyncSession,
    task_id: uuid.UUID,
    **fields,
) -> Optional[TaskRow]:
    row = await session.get(TaskRow, task_id)
    if not row:
        return None
    for key, value in fields.items():
        if value is not None and hasattr(row, key):
            setattr(row, key, value)
    if fields.get("status") == "done" and row.completed_at is None:
        row.completed_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(row)
    return row


async def delete_task(session: AsyncSession, task_id: uuid.UUID) -> bool:
    result = await session.execute(delete(TaskRow).where(TaskRow.id == task_id))
    await session.commit()
    return result.rowcount > 0


# ─── Goals ──────────────────────────────────────────────

async def create_goal(
    session: AsyncSession,
    title: str,
    target_value: Optional[float] = None,
    unit: Optional[str] = None,
    deadline: Optional[date] = None,
    category: Optional[str] = None,
    description: Optional[str] = None,
    *,
    user_id: uuid.UUID,
) -> GoalRow:
    row = GoalRow(
        user_id=user_id,
        title=title,
        description=description,
        target_value=target_value,
        unit=unit,
        deadline=deadline,
        category=category,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def get_goals(
    session: AsyncSession,
    category: Optional[str] = None,
    status: Optional[str] = None,
    *,
    user_id: uuid.UUID,
) -> list[GoalRow]:
    q = select(GoalRow).where(GoalRow.user_id == user_id)
    if category:
        q = q.where(GoalRow.category == category)
    if status:
        q = q.where(GoalRow.status == status)
    q = q.order_by(GoalRow.created_at.desc())
    result = await session.execute(q)
    return list(result.scalars().all())


async def update_goal(
    session: AsyncSession,
    goal_id: uuid.UUID,
    **fields,
) -> Optional[GoalRow]:
    row = await session.get(GoalRow, goal_id)
    if not row:
        return None
    for key, value in fields.items():
        if value is not None and hasattr(row, key):
            setattr(row, key, value)
    if row.target_value and row.current_value >= row.target_value and row.status == "active":
        row.status = "achieved"
    await session.commit()
    await session.refresh(row)
    return row


async def delete_goal(session: AsyncSession, goal_id: uuid.UUID) -> bool:
    result = await session.execute(delete(GoalRow).where(GoalRow.id == goal_id))
    await session.commit()
    return result.rowcount > 0


# ─── Habits ─────────────────────────────────────────────

async def create_habit(
    session: AsyncSession,
    name: str,
    frequency: str = "daily",
    category: Optional[str] = None,
    *,
    user_id: uuid.UUID,
) -> HabitRow:
    row = HabitRow(
        user_id=user_id,
        name=name,
        frequency=frequency,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def get_habits(session: AsyncSession, *, user_id: uuid.UUID) -> list[HabitRow]:
    result = await session.execute(
        select(HabitRow)
        .where(HabitRow.user_id == user_id)
        .order_by(HabitRow.created_at.desc())
    )
    return list(result.scalars().all())


async def check_habit(session: AsyncSession, habit_id: uuid.UUID) -> Optional[HabitRow]:
    row = await session.get(HabitRow, habit_id)
    if not row:
        return None

    today = user_today()
    if row.last_done == today:
        return row  # already checked today

    if row.last_done is not None:
        if row.frequency == "daily" and row.last_done == today - timedelta(days=1):
            row.current_streak += 1
        elif row.frequency == "weekly" and row.last_done >= today - timedelta(days=7):
            row.current_streak += 1
        else:
            row.current_streak = 1  # streak broken
    else:
        row.current_streak = 1  # first check-in

    row.best_streak = max(row.best_streak, row.current_streak)
    row.last_done = today
    await session.commit()
    await session.refresh(row)
    return row


async def delete_habit(session: AsyncSession, habit_id: uuid.UUID) -> bool:
    result = await session.execute(delete(HabitRow).where(HabitRow.id == habit_id))
    await session.commit()
    return result.rowcount > 0

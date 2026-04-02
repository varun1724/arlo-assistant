"""Reminder service — CRUD and condition evaluation."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ReminderRow, HealthDailyRow, HabitRow

import logging

logger = logging.getLogger("arlo.assistant.reminders")


async def create_reminder(
    session: AsyncSession,
    message: str,
    remind_at: Optional[datetime] = None,
    recurring: Optional[str] = None,
    smart_condition: Optional[dict] = None,
    *,
    user_id: uuid.UUID,
) -> ReminderRow:
    row = ReminderRow(
        user_id=user_id,
        message=message,
        remind_at=remind_at,
        recurring=recurring,
        smart_condition=smart_condition,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def get_reminders(
    session: AsyncSession,
    status: Optional[str] = None,
    *,
    user_id: uuid.UUID,
) -> list[ReminderRow]:
    q = select(ReminderRow).where(ReminderRow.user_id == user_id)
    if status:
        q = q.where(ReminderRow.status == status)
    q = q.order_by(ReminderRow.created_at.desc())
    result = await session.execute(q)
    return list(result.scalars().all())


async def dismiss_reminder(session: AsyncSession, reminder_id: uuid.UUID) -> Optional[ReminderRow]:
    row = await session.get(ReminderRow, reminder_id)
    if not row:
        return None
    row.status = "dismissed"
    await session.commit()
    await session.refresh(row)
    return row


async def delete_reminder(session: AsyncSession, reminder_id: uuid.UUID) -> bool:
    result = await session.execute(delete(ReminderRow).where(ReminderRow.id == reminder_id))
    await session.commit()
    return result.rowcount > 0


async def get_triggered_reminders(session: AsyncSession, *, user_id: uuid.UUID) -> list[ReminderRow]:
    """Get all reminders that should fire now (time-based or smart condition)."""
    now = datetime.now(timezone.utc)
    today = date.today()

    active = await get_reminders(session, status="active", user_id=user_id)
    triggered = []

    for r in active:
        should_fire = False

        # Time-based: remind_at has passed
        if r.remind_at and r.remind_at <= now:
            should_fire = True

        # Smart condition evaluation
        elif r.smart_condition:
            should_fire = await _evaluate_condition(session, r.smart_condition, today, now, user_id=user_id)

        if should_fire:
            triggered.append(r)

    return triggered


async def fire_reminders(session: AsyncSession, *, user_id: uuid.UUID) -> list[ReminderRow]:
    """Check and fire all triggered reminders. Returns the ones that fired."""
    triggered = await get_triggered_reminders(session, user_id=user_id)
    fired = []

    for r in triggered:
        if r.recurring:
            # Recurring: mark as fired, it will reset on next check cycle
            # For now just collect it — the prompt injection handles display
            fired.append(r)
        else:
            r.status = "fired"
            fired.append(r)

    if fired:
        await session.commit()

    return fired


async def _evaluate_condition(
    session: AsyncSession, condition: dict, today: date, now: datetime, *, user_id: uuid.UUID
) -> bool:
    """Evaluate a smart condition against current data."""
    ctype = condition.get("type", "")
    current_hour = now.hour

    # Check "after" time gate
    after_hour = condition.get("after_hour")
    if after_hour is not None and current_hour < after_hour:
        return False

    if ctype == "steps_below":
        threshold = condition.get("threshold", 5000)
        result = await session.execute(
            select(HealthDailyRow).where(
                HealthDailyRow.user_id == user_id,
                HealthDailyRow.date == today,
            )
        )
        daily = result.scalars().first()
        if daily and daily.steps < threshold:
            return True

    elif ctype == "no_meal_logged":
        from app.db.models import MealRow
        result = await session.execute(
            select(MealRow).where(
                MealRow.user_id == user_id,
                MealRow.created_at >= datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc),
            ).limit(1)
        )
        if result.scalars().first() is None:
            return True

    elif ctype == "habit_not_done":
        habit_name = condition.get("habit")
        if habit_name:
            result = await session.execute(
                select(HabitRow).where(
                    HabitRow.user_id == user_id,
                    HabitRow.name == habit_name,
                )
            )
            habit = result.scalars().first()
            if habit and habit.last_done != today:
                return True

    return False

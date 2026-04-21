"""Reminder service — CRUD and condition evaluation."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import user_today
from app.db.models import ReminderRow, HealthDailyRow, HabitRow

import logging

logger = logging.getLogger("arlo.assistant.reminders")


async def create_reminder(
    session: AsyncSession,
    message: str,
    remind_at: Optional[datetime] = None,
    recurring: Optional[str] = None,
    smart_condition: Optional[dict] = None,
    source: Optional[str] = None,
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
    # Store source tag in smart_condition for idempotency checks
    if source and row.smart_condition is None:
        row.smart_condition = {"source": source}
    elif source and row.smart_condition is not None:
        row.smart_condition = {**row.smart_condition, "source": source}
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
    today = user_today()

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
            fired.append(r)
        else:
            r.status = "fired"
            fired.append(r)

    if fired:
        await session.commit()

    return fired


async def seed_default_reminders(session: AsyncSession, *, user_id: uuid.UUID) -> list[ReminderRow]:
    """Seed default daily reminders for a new user. Idempotent."""
    # Check if already seeded
    existing = await get_reminders(session, status="active", user_id=user_id)
    seeded_sources = set()
    for r in existing:
        if r.smart_condition and r.smart_condition.get("source", "").startswith("default_"):
            seeded_sources.add(r.smart_condition["source"])

    defaults = [
        {
            "source": "default_morning",
            "message": "Good morning — ready to start your day?",
            "smart_condition": {"type": "time_of_day", "after_hour": 7, "before_hour": 10, "source": "default_morning"},
            "recurring": "daily",
        },
        {
            "source": "default_breakfast",
            "message": "Time for breakfast — what's the plan?",
            "smart_condition": {
                "type": "no_meal_logged",
                "meal_type": "breakfast",
                "after_hour": 7,
                "before_hour": 11,
                "source": "default_breakfast",
            },
            "recurring": "daily",
        },
        {
            "source": "default_lunch",
            "message": "Lunch time — log it or get a suggestion",
            "smart_condition": {
                "type": "no_meal_logged",
                "meal_type": "lunch",
                "after_hour": 11,
                "before_hour": 15,
                "source": "default_lunch",
            },
            "recurring": "daily",
        },
        {
            "source": "default_snack",
            "message": "Protein snack time — keep hitting that 200g target",
            "smart_condition": {
                "type": "no_meal_logged",
                "meal_type": "snack",
                "after_hour": 14,
                "before_hour": 17,
                "source": "default_snack",
            },
            "recurring": "daily",
        },
        {
            "source": "default_dinner",
            "message": "Dinner plan? Log it or get ideas",
            "smart_condition": {
                "type": "no_meal_logged",
                "meal_type": "dinner",
                "after_hour": 17,
                "before_hour": 21,
                "source": "default_dinner",
            },
            "recurring": "daily",
        },
        {
            "source": "default_steps",
            "message": "Step check — worth a walk before the day ends?",
            "smart_condition": {
                "type": "steps_below",
                "threshold": 8000,
                "after_hour": 20,
                "source": "default_steps",
            },
            "recurring": "daily",
        },
    ]

    created = []
    for d in defaults:
        if d["source"] in seeded_sources:
            continue
        row = ReminderRow(
            user_id=user_id,
            message=d["message"],
            recurring=d["recurring"],
            smart_condition=d["smart_condition"],
        )
        session.add(row)
        created.append(row)

    if created:
        await session.commit()
        for row in created:
            await session.refresh(row)

    return created


async def _evaluate_condition(
    session: AsyncSession, condition: dict, today: date, now: datetime, *, user_id: uuid.UUID
) -> bool:
    """Evaluate a smart condition against current data."""
    ctype = condition.get("type", "")
    current_hour = now.hour

    # "after_hour" gate — don't fire before this hour
    after_hour = condition.get("after_hour")
    if after_hour is not None and current_hour < after_hour:
        return False

    # "before_hour" gate — don't fire after this hour
    before_hour = condition.get("before_hour")
    if before_hour is not None and current_hour >= before_hour:
        return False

    if ctype == "time_of_day":
        # Fires once per day in the configured window
        return True

    elif ctype == "steps_below":
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
        meal_type = condition.get("meal_type")
        q = select(MealRow).where(
            MealRow.user_id == user_id,
            MealRow.date == today,
        )
        if meal_type:
            q = q.where(MealRow.meal_type == meal_type)
        q = q.limit(1)
        result = await session.execute(q)
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

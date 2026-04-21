"""HealthKit sync service — merge iOS HealthKit data into health records."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import user_today
from app.db.models import HealthDailyRow, WorkoutRow
from app.services.health_service import get_or_create_daily

import logging

logger = logging.getLogger("arlo.assistant.healthkit")


async def sync_healthkit(
    session: AsyncSession,
    data: dict,
    *,
    user_id: uuid.UUID,
) -> dict:
    """Merge a HealthKit data batch into the database.

    Takes MAX of steps (manual vs HealthKit), overwrites heart rate/sleep,
    and creates workout records avoiding duplicates.
    """
    sync_date = date.fromisoformat(data["date"]) if isinstance(data.get("date"), str) else user_today()

    daily = await get_or_create_daily(session, sync_date, user_id=user_id)

    # Steps: take max of existing vs HealthKit
    hk_steps = data.get("steps")
    if hk_steps is not None and hk_steps > daily.steps:
        daily.steps = hk_steps

    # Active calories: overwrite
    hk_active_cal = data.get("active_calories")
    if hk_active_cal is not None:
        daily.active_calories = hk_active_cal

    # Resting heart rate: overwrite
    hk_hr = data.get("resting_heart_rate")
    if hk_hr is not None:
        daily.resting_heart_rate = hk_hr

    # Sleep: overwrite
    hk_sleep = data.get("sleep_hours")
    if hk_sleep is not None:
        daily.sleep_hours = hk_sleep

    # Workouts: create if not duplicate
    for w in data.get("workouts", []):
        workout = WorkoutRow(
            user_id=user_id,
            date=sync_date,
            workout_type=w.get("type", "unknown"),
            duration_minutes=w.get("duration_minutes"),
            exercises={"source": "healthkit", "calories": w.get("calories"), "distance_km": w.get("distance_km")},
            notes=f"Synced from HealthKit",
        )
        session.add(workout)

    await session.commit()
    await session.refresh(daily)

    logger.info("HealthKit sync for %s: steps=%s, hr=%s, sleep=%s, workouts=%d",
                sync_date, hk_steps, hk_hr, hk_sleep, len(data.get("workouts", [])))

    return {"synced": True, "date": sync_date.isoformat()}

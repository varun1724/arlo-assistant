"""Health service — step tracking, meals, workouts, daily summaries."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import HealthDailyRow, MealRow, WorkoutRow, GoalRow
from app.services.chat_service import DEFAULT_USER_ID

import logging

logger = logging.getLogger("arlo.assistant.health")


# ─── Daily Health ────────────────────────────────────────

async def get_or_create_daily(session: AsyncSession, target_date: date | None = None) -> HealthDailyRow:
    """Get or create today's health record."""
    if target_date is None:
        target_date = date.today()

    result = await session.execute(
        select(HealthDailyRow).where(
            HealthDailyRow.user_id == DEFAULT_USER_ID,
            HealthDailyRow.date == target_date,
        )
    )
    row = result.scalars().first()
    if row:
        return row

    row = HealthDailyRow(user_id=DEFAULT_USER_ID, date=target_date)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def log_steps(session: AsyncSession, steps: int, target_date: date | None = None) -> HealthDailyRow:
    """Log step count for a day (replaces existing value)."""
    daily = await get_or_create_daily(session, target_date)
    await session.execute(
        update(HealthDailyRow)
        .where(HealthDailyRow.id == daily.id)
        .values(steps=steps)
    )
    await session.commit()
    await session.refresh(daily)
    return daily


async def update_daily_macros(session: AsyncSession, target_date: date | None = None) -> HealthDailyRow:
    """Recalculate daily totals from all meals logged today."""
    if target_date is None:
        target_date = date.today()

    daily = await get_or_create_daily(session, target_date)

    # Sum all meals for today
    result = await session.execute(
        select(
            func.coalesce(func.sum(MealRow.calories), 0),
            func.coalesce(func.sum(MealRow.protein_g), 0),
            func.coalesce(func.sum(MealRow.carbs_g), 0),
            func.coalesce(func.sum(MealRow.fat_g), 0),
        ).where(
            MealRow.user_id == DEFAULT_USER_ID,
            MealRow.date == target_date,
        )
    )
    totals = result.one()

    await session.execute(
        update(HealthDailyRow)
        .where(HealthDailyRow.id == daily.id)
        .values(
            calories=float(totals[0]),
            protein_g=float(totals[1]),
            carbs_g=float(totals[2]),
            fat_g=float(totals[3]),
        )
    )
    await session.commit()
    await session.refresh(daily)
    return daily


# ─── Meals ───────────────────────────────────────────────

async def log_meal(
    session: AsyncSession,
    description: str,
    calories: float = 0,
    protein_g: float = 0,
    carbs_g: float = 0,
    fat_g: float = 0,
    meal_type: str = "other",
    target_date: date | None = None,
) -> MealRow:
    """Log a meal and update daily totals."""
    if target_date is None:
        target_date = date.today()

    row = MealRow(
        user_id=DEFAULT_USER_ID,
        date=target_date,
        meal_type=meal_type,
        description=description,
        calories=calories,
        protein_g=protein_g,
        carbs_g=carbs_g,
        fat_g=fat_g,
    )
    session.add(row)
    await session.commit()

    # Update daily totals
    await update_daily_macros(session, target_date)

    await session.refresh(row)
    return row


async def get_meals(session: AsyncSession, target_date: date | None = None) -> list[MealRow]:
    """Get all meals for a day."""
    if target_date is None:
        target_date = date.today()

    result = await session.execute(
        select(MealRow)
        .where(MealRow.user_id == DEFAULT_USER_ID, MealRow.date == target_date)
        .order_by(MealRow.created_at.asc())
    )
    return list(result.scalars().all())


# ─── Workouts ────────────────────────────────────────────

async def log_workout(
    session: AsyncSession,
    workout_type: str,
    exercises: dict | None = None,
    duration_minutes: int | None = None,
    notes: str | None = None,
    target_date: date | None = None,
) -> WorkoutRow:
    """Log a workout."""
    if target_date is None:
        target_date = date.today()

    row = WorkoutRow(
        user_id=DEFAULT_USER_ID,
        date=target_date,
        workout_type=workout_type,
        exercises=exercises,
        duration_minutes=duration_minutes,
        notes=notes,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def get_workouts(session: AsyncSession, target_date: date | None = None) -> list[WorkoutRow]:
    """Get all workouts for a day."""
    if target_date is None:
        target_date = date.today()

    result = await session.execute(
        select(WorkoutRow)
        .where(WorkoutRow.user_id == DEFAULT_USER_ID, WorkoutRow.date == target_date)
        .order_by(WorkoutRow.created_at.asc())
    )
    return list(result.scalars().all())


# ─── Dashboard ───────────────────────────────────────────

async def get_dashboard(session: AsyncSession, target_date: date | None = None) -> dict:
    """Get today's health dashboard with stats vs goals."""
    if target_date is None:
        target_date = date.today()

    daily = await get_or_create_daily(session, target_date)
    meals = await get_meals(session, target_date)
    workouts = await get_workouts(session, target_date)

    # Get health goals
    goals = {}
    result = await session.execute(
        select(GoalRow).where(
            GoalRow.user_id == DEFAULT_USER_ID,
            GoalRow.category == "health",
            GoalRow.status == "active",
        )
    )
    for g in result.scalars().all():
        goals[g.title] = {"target": g.target_value, "unit": g.unit}

    return {
        "date": target_date.isoformat(),
        "steps": daily.steps,
        "calories": daily.calories,
        "protein_g": daily.protein_g,
        "carbs_g": daily.carbs_g,
        "fat_g": daily.fat_g,
        "water_oz": daily.water_oz,
        "sleep_hours": daily.sleep_hours,
        "mood": daily.mood,
        "meals_logged": len(meals),
        "workouts_logged": len(workouts),
        "workouts": [
            {"type": w.workout_type, "duration": w.duration_minutes, "exercises": w.exercises}
            for w in workouts
        ],
        "goals": goals,
    }


async def get_weekly_summary(session: AsyncSession) -> dict:
    """Get the past 7 days of health data."""
    from datetime import timedelta
    today = date.today()
    week_ago = today - timedelta(days=7)

    result = await session.execute(
        select(HealthDailyRow)
        .where(
            HealthDailyRow.user_id == DEFAULT_USER_ID,
            HealthDailyRow.date >= week_ago,
            HealthDailyRow.date <= today,
        )
        .order_by(HealthDailyRow.date.asc())
    )
    days = result.scalars().all()

    # Count workouts this week
    workout_result = await session.execute(
        select(func.count()).select_from(WorkoutRow).where(
            WorkoutRow.user_id == DEFAULT_USER_ID,
            WorkoutRow.date >= week_ago,
        )
    )
    workout_count = workout_result.scalar_one()

    daily_data = [
        {
            "date": d.date.isoformat(),
            "steps": d.steps,
            "calories": d.calories,
            "protein_g": d.protein_g,
        }
        for d in days
    ]

    avg_steps = sum(d.steps for d in days) / max(len(days), 1)
    avg_protein = sum(d.protein_g for d in days) / max(len(days), 1)
    avg_calories = sum(d.calories for d in days) / max(len(days), 1)

    return {
        "period": f"{week_ago.isoformat()} to {today.isoformat()}",
        "days_logged": len(days),
        "workouts": workout_count,
        "averages": {
            "steps": round(avg_steps),
            "calories": round(avg_calories),
            "protein_g": round(avg_protein, 1),
        },
        "daily": daily_data,
    }

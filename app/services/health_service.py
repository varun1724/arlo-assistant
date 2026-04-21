"""Health service — step tracking, meals, workouts, daily summaries."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import user_today
from app.db.models import HealthDailyRow, MealRow, WorkoutRow, GoalRow, KnowledgeRow, UserProfileRow, GroceryListRow, RecipeRow

import logging

logger = logging.getLogger("arlo.assistant.health")


# ─── Daily Health ────────────────────────────────────────

async def get_or_create_daily(session: AsyncSession, target_date: date | None = None, *, user_id: uuid.UUID) -> HealthDailyRow:
    """Get or create today's health record."""
    if target_date is None:
        target_date = user_today()

    result = await session.execute(
        select(HealthDailyRow).where(
            HealthDailyRow.user_id == user_id,
            HealthDailyRow.date == target_date,
        )
    )
    row = result.scalars().first()
    if row:
        return row

    row = HealthDailyRow(user_id=user_id, date=target_date)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def log_steps(session: AsyncSession, steps: int, target_date: date | None = None, *, user_id: uuid.UUID) -> HealthDailyRow:
    """Log step count for a day (replaces existing value)."""
    daily = await get_or_create_daily(session, target_date, user_id=user_id)
    await session.execute(
        update(HealthDailyRow)
        .where(HealthDailyRow.id == daily.id)
        .values(steps=steps)
    )
    await session.commit()
    await session.refresh(daily)
    return daily


async def update_daily_macros(session: AsyncSession, target_date: date | None = None, *, user_id: uuid.UUID) -> HealthDailyRow:
    """Recalculate daily totals from all meals logged today."""
    if target_date is None:
        target_date = user_today()

    daily = await get_or_create_daily(session, target_date, user_id=user_id)

    # Sum all meals for today
    result = await session.execute(
        select(
            func.coalesce(func.sum(MealRow.calories), 0),
            func.coalesce(func.sum(MealRow.protein_g), 0),
            func.coalesce(func.sum(MealRow.carbs_g), 0),
            func.coalesce(func.sum(MealRow.fat_g), 0),
        ).where(
            MealRow.user_id == user_id,
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
    *,
    user_id: uuid.UUID,
) -> MealRow:
    """Log a meal and update daily totals."""
    if target_date is None:
        target_date = user_today()

    row = MealRow(
        user_id=user_id,
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
    await update_daily_macros(session, target_date, user_id=user_id)

    await session.refresh(row)
    return row


async def get_meals(session: AsyncSession, target_date: date | None = None, *, user_id: uuid.UUID) -> list[MealRow]:
    """Get all meals for a day."""
    if target_date is None:
        target_date = user_today()

    result = await session.execute(
        select(MealRow)
        .where(MealRow.user_id == user_id, MealRow.date == target_date)
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
    *,
    user_id: uuid.UUID,
) -> WorkoutRow:
    """Log a workout."""
    if target_date is None:
        target_date = user_today()

    row = WorkoutRow(
        user_id=user_id,
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


async def get_workouts(session: AsyncSession, target_date: date | None = None, *, user_id: uuid.UUID) -> list[WorkoutRow]:
    """Get all workouts for a day."""
    if target_date is None:
        target_date = user_today()

    result = await session.execute(
        select(WorkoutRow)
        .where(WorkoutRow.user_id == user_id, WorkoutRow.date == target_date)
        .order_by(WorkoutRow.created_at.asc())
    )
    return list(result.scalars().all())


# ─── Dashboard ───────────────────────────────────────────

async def get_dashboard(session: AsyncSession, target_date: date | None = None, *, user_id: uuid.UUID) -> dict:
    """Get today's health dashboard with stats vs goals.

    Macros are aggregated directly from MealRow on every request so the
    dashboard can never drift from the underlying meal records.
    """
    if target_date is None:
        target_date = user_today()

    daily = await get_or_create_daily(session, target_date, user_id=user_id)
    meals = await get_meals(session, target_date, user_id=user_id)
    workouts = await get_workouts(session, target_date, user_id=user_id)

    # Sum macros directly from meals for this date (authoritative source)
    macro_totals = await session.execute(
        select(
            func.coalesce(func.sum(MealRow.calories), 0),
            func.coalesce(func.sum(MealRow.protein_g), 0),
            func.coalesce(func.sum(MealRow.carbs_g), 0),
            func.coalesce(func.sum(MealRow.fat_g), 0),
        ).where(
            MealRow.user_id == user_id,
            MealRow.date == target_date,
        )
    )
    calories, protein_g, carbs_g, fat_g = macro_totals.one()

    # Get health goals
    goals = {}
    result = await session.execute(
        select(GoalRow).where(
            GoalRow.user_id == user_id,
            GoalRow.category == "health",
            GoalRow.status == "active",
        )
    )
    for g in result.scalars().all():
        goals[g.title] = {"target": g.target_value, "unit": g.unit}

    return {
        "date": target_date.isoformat(),
        "steps": daily.steps,
        "calories": float(calories),
        "protein_g": float(protein_g),
        "carbs_g": float(carbs_g),
        "fat_g": float(fat_g),
        "water_oz": daily.water_oz,
        "sleep_hours": daily.sleep_hours,
        "resting_heart_rate": daily.resting_heart_rate,
        "active_calories": daily.active_calories,
        "mood": daily.mood,
        "meals_logged": len(meals),
        "workouts_logged": len(workouts),
        "workouts": [
            {"type": w.workout_type, "duration": w.duration_minutes, "exercises": w.exercises}
            for w in workouts
        ],
        "goals": goals,
    }


async def get_or_generate_meal_plan(
    session: AsyncSession,
    target_date: date | None = None,
    *,
    user_id: uuid.UUID,
) -> dict:
    """Return today's meal plan from cache or generate via Claude."""
    if target_date is None:
        target_date = user_today()
    date_str = target_date.isoformat()

    # Check cache first
    cached = await session.execute(
        select(KnowledgeRow).where(
            KnowledgeRow.user_id == user_id,
            KnowledgeRow.category == "meal_plan",
            KnowledgeRow.tags["date"].astext == date_str,
        ).limit(1)
    )
    row = cached.scalars().first()
    if row:
        import json as _json
        try:
            return _json.loads(row.content)
        except Exception:
            pass

    # Generate via Claude
    plan = await _generate_meal_plan_via_claude(session, target_date, user_id=user_id)

    # Cache it
    import json as _json
    knowledge = KnowledgeRow(
        user_id=user_id,
        category="meal_plan",
        content=_json.dumps(plan),
        tags={"date": date_str},
    )
    session.add(knowledge)
    await session.commit()
    return plan


async def _generate_meal_plan_via_claude(
    session: AsyncSession,
    target_date: date,
    *,
    user_id: uuid.UUID,
) -> dict:
    """Ask Claude to generate a meal plan for the day based on user goals."""
    import json as _json

    # Gather context
    daily = await get_or_create_daily(session, target_date, user_id=user_id)
    already_logged_protein = daily.protein_g
    already_logged_calories = daily.calories

    # Get user goals
    goals_result = await session.execute(
        select(GoalRow).where(
            GoalRow.user_id == user_id,
            GoalRow.status == "active",
        )
    )
    goals = {g.title: f"{g.target_value}{g.unit}" for g in goals_result.scalars().all()}
    protein_goal = goals.get("Daily Protein", "200g")
    calorie_goal = goals.get("Daily Calories", "3000kcal")

    # Get dietary preferences from profile
    prefs_result = await session.execute(
        select(UserProfileRow).where(
            UserProfileRow.user_id == user_id,
            UserProfileRow.category == "nutrition",
        )
    )
    prefs = {p.key: p.value for p in prefs_result.scalars().all()}
    dietary_notes = prefs.get("dietary_preferences", "none specified")

    # Get active grocery list items (first list)
    grocery_result = await session.execute(
        select(GroceryListRow).where(GroceryListRow.user_id == user_id).limit(1)
    )
    grocery = grocery_result.scalars().first()
    grocery_items = []
    if grocery and grocery.items:
        grocery_items = [
            item.get("item", "") for item in grocery.items
            if not item.get("checked", False)
        ][:10]

    # Get saved recipes for reference
    recipes_result = await session.execute(
        select(RecipeRow).where(RecipeRow.user_id == user_id).limit(5)
    )
    recipe_names = [r.name for r in recipes_result.scalars().all()]

    prompt = f"""Generate a meal plan for today ({target_date.isoformat()}) for a person focused on muscle gain.

Daily targets:
- Protein: {protein_goal}
- Calories: {calorie_goal}
- Already logged today: {already_logged_protein:.0f}g protein, {already_logged_calories:.0f} kcal

Dietary preferences/restrictions: {dietary_notes}
Available groceries (prefer these): {', '.join(grocery_items) if grocery_items else 'not specified'}
Saved recipes to consider: {', '.join(recipe_names) if recipe_names else 'none saved yet'}

Respond ONLY with a valid JSON object (no markdown, no explanation) in this exact format:
{{
  "date": "{target_date.isoformat()}",
  "breakfast": {{"name": "...", "calories": 0, "protein_g": 0}},
  "lunch": {{"name": "...", "calories": 0, "protein_g": 0}},
  "dinner": {{"name": "...", "calories": 0, "protein_g": 0}},
  "snacks": [{{"name": "...", "calories": 0, "protein_g": 0}}],
  "total_calories": 0,
  "total_protein_g": 0
}}

Make meal suggestions practical, high-protein, and specific. Include estimated macros."""

    from app.llm.claude import chat_with_claude, ClaudeError
    try:
        raw = await chat_with_claude(prompt, timeout=60)
        # Strip markdown fences if present
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        plan = _json.loads(raw.strip())
        plan["date"] = target_date.isoformat()
        return plan
    except (ClaudeError, _json.JSONDecodeError, Exception):
        # Fallback: return a simple default plan
        return {
            "date": target_date.isoformat(),
            "breakfast": {"name": "Greek yogurt + oats + protein powder", "calories": 550, "protein_g": 45},
            "lunch": {"name": "Chicken breast + rice + broccoli", "calories": 750, "protein_g": 55},
            "dinner": {"name": "Salmon + sweet potato + vegetables", "calories": 850, "protein_g": 50},
            "snacks": [{"name": "Cottage cheese + fruit", "calories": 300, "protein_g": 25}],
            "total_calories": 2450,
            "total_protein_g": 175,
        }


async def get_weekly_summary(session: AsyncSession, *, user_id: uuid.UUID) -> dict:
    """Get the past 7 days of health data."""
    from datetime import timedelta
    today = user_today()
    week_ago = today - timedelta(days=7)

    result = await session.execute(
        select(HealthDailyRow)
        .where(
            HealthDailyRow.user_id == user_id,
            HealthDailyRow.date >= week_ago,
            HealthDailyRow.date <= today,
        )
        .order_by(HealthDailyRow.date.asc())
    )
    days = result.scalars().all()

    # Count workouts this week
    workout_result = await session.execute(
        select(func.count()).select_from(WorkoutRow).where(
            WorkoutRow.user_id == user_id,
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

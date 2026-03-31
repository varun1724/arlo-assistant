"""Health API — steps, meals, workouts, dashboard."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_token
from app.db.engine import get_db
from app.services import health_service

router = APIRouter(prefix="/health", tags=["health"], dependencies=[Depends(verify_token)])


# ─── Request models ──────────────────────────────────────

class LogStepsRequest(BaseModel):
    steps: int = Field(..., ge=0)
    date: date | None = None


class LogMealRequest(BaseModel):
    description: str = Field(..., min_length=1)
    calories: float = 0
    protein_g: float = 0
    carbs_g: float = 0
    fat_g: float = 0
    meal_type: str = "other"
    date: date | None = None


class LogWorkoutRequest(BaseModel):
    workout_type: str = Field(..., min_length=1)
    exercises: dict | None = None
    duration_minutes: int | None = None
    notes: str | None = None
    date: date | None = None


# ─── Endpoints ───────────────────────────────────────────

@router.post("/steps")
async def log_steps(body: LogStepsRequest, db: AsyncSession = Depends(get_db)):
    daily = await health_service.log_steps(db, body.steps, body.date)
    return {"date": daily.date.isoformat(), "steps": daily.steps}


@router.post("/meals")
async def log_meal(body: LogMealRequest, db: AsyncSession = Depends(get_db)):
    meal = await health_service.log_meal(
        db,
        description=body.description,
        calories=body.calories,
        protein_g=body.protein_g,
        carbs_g=body.carbs_g,
        fat_g=body.fat_g,
        meal_type=body.meal_type,
        target_date=body.date,
    )
    return {
        "id": str(meal.id),
        "description": meal.description,
        "calories": meal.calories,
        "protein_g": meal.protein_g,
        "carbs_g": meal.carbs_g,
        "fat_g": meal.fat_g,
    }


@router.post("/workouts")
async def log_workout(body: LogWorkoutRequest, db: AsyncSession = Depends(get_db)):
    workout = await health_service.log_workout(
        db,
        workout_type=body.workout_type,
        exercises=body.exercises,
        duration_minutes=body.duration_minutes,
        notes=body.notes,
        target_date=body.date,
    )
    return {
        "id": str(workout.id),
        "type": workout.workout_type,
        "duration_minutes": workout.duration_minutes,
    }


@router.get("/meals")
async def get_meals(
    target_date: date | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    meals = await health_service.get_meals(db, target_date)
    return {
        "meals": [
            {
                "id": str(m.id),
                "meal_type": m.meal_type,
                "description": m.description,
                "calories": m.calories,
                "protein_g": m.protein_g,
                "carbs_g": m.carbs_g,
                "fat_g": m.fat_g,
                "created_at": m.created_at.isoformat(),
            }
            for m in meals
        ],
        "count": len(meals),
    }


@router.get("/dashboard")
async def dashboard(
    target_date: date | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    return await health_service.get_dashboard(db, target_date)


@router.get("/weekly")
async def weekly_summary(db: AsyncSession = Depends(get_db)):
    return await health_service.get_weekly_summary(db)
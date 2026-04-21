"""Health API — steps, meals, workouts, dashboard."""

import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.engine import get_db
from app.services import health_service

router = APIRouter(prefix="/health", tags=["health"])


# ─── Request models ──────────────────────────────────────

class LogStepsRequest(BaseModel):
    steps: int = Field(..., ge=0)
    date: Optional[date] = None


class LogMealRequest(BaseModel):
    description: str = Field(..., min_length=1)
    calories: float = 0
    protein_g: float = 0
    carbs_g: float = 0
    fat_g: float = 0
    meal_type: str = "other"
    date: Optional[date] = None


class LogWorkoutRequest(BaseModel):
    workout_type: str = Field(..., min_length=1)
    exercises: Optional[dict] = None
    duration_minutes: Optional[int] = None
    notes: Optional[str] = None
    date: Optional[date] = None


# ─── Endpoints ───────────────────────────────────────────

@router.post("/steps")
async def log_steps(body: LogStepsRequest, db: AsyncSession = Depends(get_db), user_id: uuid.UUID = Depends(get_current_user)):
    daily = await health_service.log_steps(db, body.steps, body.date, user_id=user_id)
    return {"date": daily.date.isoformat(), "steps": daily.steps}


@router.post("/meals")
async def log_meal(body: LogMealRequest, db: AsyncSession = Depends(get_db), user_id: uuid.UUID = Depends(get_current_user)):
    meal = await health_service.log_meal(
        db,
        description=body.description.strip(),
        calories=body.calories,
        protein_g=body.protein_g,
        carbs_g=body.carbs_g,
        fat_g=body.fat_g,
        meal_type=body.meal_type,
        target_date=body.date,
        user_id=user_id,
    )
    return {
        "id": str(meal.id),
        "meal_type": meal.meal_type,
        "description": meal.description,
        "calories": meal.calories,
        "protein_g": meal.protein_g,
        "carbs_g": meal.carbs_g,
        "fat_g": meal.fat_g,
        "created_at": meal.created_at.isoformat(),
    }


@router.post("/workouts")
async def log_workout(body: LogWorkoutRequest, db: AsyncSession = Depends(get_db), user_id: uuid.UUID = Depends(get_current_user)):
    workout = await health_service.log_workout(
        db,
        workout_type=body.workout_type,
        exercises=body.exercises,
        duration_minutes=body.duration_minutes,
        notes=body.notes,
        target_date=body.date,
        user_id=user_id,
    )
    return {
        "id": str(workout.id),
        "type": workout.workout_type,
        "duration_minutes": workout.duration_minutes,
    }


@router.get("/meals")
async def get_meals(
    target_date: Optional[date] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user),
):
    meals = await health_service.get_meals(db, target_date, user_id=user_id)
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
    target_date: Optional[date] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user),
):
    return await health_service.get_dashboard(db, target_date, user_id=user_id)


@router.get("/weekly")
async def weekly_summary(db: AsyncSession = Depends(get_db), user_id: uuid.UUID = Depends(get_current_user)):
    return await health_service.get_weekly_summary(db, user_id=user_id)


@router.get("/meal-plan")
async def get_meal_plan(
    target_date: Optional[date] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user),
):
    """Return today's meal plan, generating via Claude if not yet created."""
    return await health_service.get_or_generate_meal_plan(db, target_date, user_id=user_id)
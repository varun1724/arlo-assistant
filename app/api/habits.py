"""Habits API — create, list, check-in, delete habits."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.engine import get_db
from app.services import task_service

router = APIRouter(prefix="/habits", tags=["habits"])


class CreateHabitRequest(BaseModel):
    name: str = Field(..., min_length=1)
    frequency: str = "daily"


@router.post("", status_code=201)
async def create_habit(body: CreateHabitRequest, db: AsyncSession = Depends(get_db), user_id: uuid.UUID = Depends(get_current_user)):
    habit = await task_service.create_habit(db, name=body.name, frequency=body.frequency, user_id=user_id)
    return _habit_response(habit)


@router.get("")
async def list_habits(db: AsyncSession = Depends(get_db), user_id: uuid.UUID = Depends(get_current_user)):
    habits = await task_service.get_habits(db, user_id=user_id)
    return {"habits": [_habit_response(h) for h in habits], "count": len(habits)}


@router.patch("/{habit_id}/check")
async def check_habit(habit_id: uuid.UUID, db: AsyncSession = Depends(get_db), user_id: uuid.UUID = Depends(get_current_user)):
    habit = await task_service.check_habit(db, habit_id, user_id=user_id)
    if not habit:
        raise HTTPException(status_code=404, detail="Habit not found")
    return _habit_response(habit)


@router.delete("/{habit_id}")
async def delete_habit(habit_id: uuid.UUID, db: AsyncSession = Depends(get_db), user_id: uuid.UUID = Depends(get_current_user)):
    deleted = await task_service.delete_habit(db, habit_id, user_id=user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Habit not found")
    return {"deleted": True}


def _habit_response(h) -> dict:
    return {
        "id": str(h.id),
        "name": h.name,
        "frequency": h.frequency,
        "current_streak": h.current_streak,
        "best_streak": h.best_streak,
        "last_done": h.last_done.isoformat() if h.last_done else None,
        "created_at": h.created_at.isoformat(),
    }

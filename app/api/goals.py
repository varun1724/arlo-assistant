"""Goals API — create, list, update, delete goals."""

import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.engine import get_db
from app.services import task_service

router = APIRouter(prefix="/goals", tags=["goals"])


class CreateGoalRequest(BaseModel):
    title: str = Field(..., min_length=1)
    description: Optional[str] = None
    target_value: Optional[float] = None
    unit: Optional[str] = None
    deadline: Optional[date] = None
    category: Optional[str] = None


class UpdateGoalRequest(BaseModel):
    current_value: Optional[float] = None
    target_value: Optional[float] = None
    status: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    unit: Optional[str] = None
    category: Optional[str] = None
    deadline: Optional[date] = None


@router.post("", status_code=201)
async def create_goal(body: CreateGoalRequest, db: AsyncSession = Depends(get_db), user_id: uuid.UUID = Depends(get_current_user)):
    goal = await task_service.create_goal(
        db, title=body.title, description=body.description,
        target_value=body.target_value, unit=body.unit,
        deadline=body.deadline, category=body.category,
        user_id=user_id,
    )
    return _goal_response(goal)


@router.get("")
async def list_goals(
    category: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user),
):
    goals = await task_service.get_goals(db, category=category, status=status, user_id=user_id)
    return {"goals": [_goal_response(g) for g in goals], "count": len(goals)}


@router.patch("/{goal_id}")
async def update_goal(goal_id: uuid.UUID, body: UpdateGoalRequest, db: AsyncSession = Depends(get_db), user_id: uuid.UUID = Depends(get_current_user)):
    fields = body.model_dump(exclude_unset=True)
    goal = await task_service.update_goal(db, goal_id, user_id=user_id, **fields)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    return _goal_response(goal)


@router.delete("/{goal_id}")
async def delete_goal(goal_id: uuid.UUID, db: AsyncSession = Depends(get_db), user_id: uuid.UUID = Depends(get_current_user)):
    deleted = await task_service.delete_goal(db, goal_id, user_id=user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Goal not found")
    return {"deleted": True}


def _goal_response(g) -> dict:
    return {
        "id": str(g.id),
        "title": g.title,
        "description": g.description,
        "target_value": g.target_value,
        "current_value": g.current_value,
        "unit": g.unit,
        "deadline": g.deadline.isoformat() if g.deadline else None,
        "status": g.status,
        "category": g.category,
        "created_at": g.created_at.isoformat(),
    }

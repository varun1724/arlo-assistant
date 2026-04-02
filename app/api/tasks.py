"""Tasks API — create, list, update, delete tasks."""

import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.engine import get_db
from app.services import task_service

router = APIRouter(prefix="/tasks", tags=["tasks"])


class CreateTaskRequest(BaseModel):
    title: str = Field(..., min_length=1)
    description: Optional[str] = None
    priority: str = "medium"
    due_date: Optional[date] = None
    category: Optional[str] = None
    recurring: Optional[str] = None


class UpdateTaskRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[date] = None
    category: Optional[str] = None


@router.post("", status_code=201)
async def create_task(body: CreateTaskRequest, db: AsyncSession = Depends(get_db), user_id: uuid.UUID = Depends(get_current_user)):
    task = await task_service.create_task(
        db, title=body.title, description=body.description,
        priority=body.priority, due_date=body.due_date,
        category=body.category, recurring=body.recurring,
        user_id=user_id,
    )
    return _task_response(task)


@router.get("")
async def list_tasks(
    status: Optional[str] = Query(default=None),
    priority: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user),
):
    tasks = await task_service.get_tasks(db, status=status, priority=priority, category=category, user_id=user_id)
    return {"tasks": [_task_response(t) for t in tasks], "count": len(tasks)}


@router.patch("/{task_id}")
async def update_task(task_id: uuid.UUID, body: UpdateTaskRequest, db: AsyncSession = Depends(get_db), user_id: uuid.UUID = Depends(get_current_user)):
    fields = body.model_dump(exclude_unset=True)
    task = await task_service.update_task(db, task_id, **fields)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return _task_response(task)


@router.delete("/{task_id}")
async def delete_task(task_id: uuid.UUID, db: AsyncSession = Depends(get_db), user_id: uuid.UUID = Depends(get_current_user)):
    deleted = await task_service.delete_task(db, task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"deleted": True}


def _task_response(t) -> dict:
    return {
        "id": str(t.id),
        "title": t.title,
        "description": t.description,
        "status": t.status,
        "priority": t.priority,
        "due_date": t.due_date.isoformat() if t.due_date else None,
        "category": t.category,
        "recurring": t.recurring,
        "created_at": t.created_at.isoformat(),
        "completed_at": t.completed_at.isoformat() if t.completed_at else None,
    }

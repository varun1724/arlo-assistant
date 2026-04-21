"""Reminders API — create, list, dismiss, delete reminders."""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.engine import get_db
from app.services import reminder_service

router = APIRouter(prefix="/reminders", tags=["reminders"])


class CreateReminderRequest(BaseModel):
    message: str = Field(..., min_length=1)
    remind_at: Optional[datetime] = None
    recurring: Optional[str] = None
    smart_condition: Optional[dict] = None


@router.post("", status_code=201)
async def create_reminder(body: CreateReminderRequest, db: AsyncSession = Depends(get_db), user_id: uuid.UUID = Depends(get_current_user)):
    reminder = await reminder_service.create_reminder(
        db, message=body.message, remind_at=body.remind_at,
        recurring=body.recurring, smart_condition=body.smart_condition,
        user_id=user_id,
    )
    return _reminder_response(reminder)


@router.get("")
async def list_reminders(
    status: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user),
):
    reminders = await reminder_service.get_reminders(db, status=status, user_id=user_id)
    return {"reminders": [_reminder_response(r) for r in reminders], "count": len(reminders)}


@router.get("/triggered")
async def get_triggered(db: AsyncSession = Depends(get_db), user_id: uuid.UUID = Depends(get_current_user)):
    triggered = await reminder_service.get_triggered_reminders(db, user_id=user_id)
    return {"reminders": [_reminder_response(r) for r in triggered], "count": len(triggered)}


@router.patch("/{reminder_id}/dismiss")
async def dismiss_reminder(reminder_id: uuid.UUID, db: AsyncSession = Depends(get_db), user_id: uuid.UUID = Depends(get_current_user)):
    reminder = await reminder_service.dismiss_reminder(db, reminder_id, user_id=user_id)
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")
    return _reminder_response(reminder)


@router.delete("/{reminder_id}")
async def delete_reminder(reminder_id: uuid.UUID, db: AsyncSession = Depends(get_db), user_id: uuid.UUID = Depends(get_current_user)):
    deleted = await reminder_service.delete_reminder(db, reminder_id, user_id=user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Reminder not found")
    return {"deleted": True}


@router.post("/seed-defaults", status_code=201)
async def seed_default_reminders(db: AsyncSession = Depends(get_db), user_id: uuid.UUID = Depends(get_current_user)):
    """Seed default meal + health reminders. Idempotent — skips already-seeded ones."""
    created = await reminder_service.seed_default_reminders(db, user_id=user_id)
    return {"created": len(created), "reminders": [_reminder_response(r) for r in created]}


def _reminder_response(r) -> dict:
    return {
        "id": str(r.id),
        "message": r.message,
        "remind_at": r.remind_at.isoformat() if r.remind_at else None,
        "recurring": r.recurring,
        "smart_condition": r.smart_condition,
        "status": r.status,
        "created_at": r.created_at.isoformat(),
    }

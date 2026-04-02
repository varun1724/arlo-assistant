"""Calendar API — events and scheduling."""

import uuid
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.engine import get_db
from app.services import calendar_service

router = APIRouter(prefix="/calendar", tags=["calendar"])


class CreateEventRequest(BaseModel):
    title: str = Field(..., min_length=1)
    start_time: datetime
    end_time: Optional[datetime] = None
    description: Optional[str] = None
    location: Optional[str] = None
    recurring: Optional[str] = None


class UpdateEventRequest(BaseModel):
    title: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    description: Optional[str] = None
    location: Optional[str] = None


@router.post("/events", status_code=201)
async def create_event(body: CreateEventRequest, db: AsyncSession = Depends(get_db), user_id: uuid.UUID = Depends(get_current_user)):
    event = await calendar_service.create_event(
        db, title=body.title, start_time=body.start_time,
        end_time=body.end_time, description=body.description,
        location=body.location, recurring=body.recurring,
        user_id=user_id,
    )
    return _event_response(event)


@router.get("/events")
async def list_events(
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user),
):
    events = await calendar_service.get_events(db, start_date=start_date, end_date=end_date, user_id=user_id)
    return {"events": [_event_response(e) for e in events], "count": len(events)}


@router.get("/events/today")
async def today_events(db: AsyncSession = Depends(get_db), user_id: uuid.UUID = Depends(get_current_user)):
    events = await calendar_service.get_today_events(db, user_id=user_id)
    return {"events": [_event_response(e) for e in events], "count": len(events)}


@router.patch("/events/{event_id}")
async def update_event(event_id: uuid.UUID, body: UpdateEventRequest, db: AsyncSession = Depends(get_db), user_id: uuid.UUID = Depends(get_current_user)):
    fields = body.model_dump(exclude_unset=True)
    event = await calendar_service.update_event(db, event_id, **fields)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return _event_response(event)


@router.delete("/events/{event_id}")
async def delete_event(event_id: uuid.UUID, db: AsyncSession = Depends(get_db), user_id: uuid.UUID = Depends(get_current_user)):
    deleted = await calendar_service.delete_event(db, event_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Event not found")
    return {"deleted": True}


def _event_response(e) -> dict:
    return {
        "id": str(e.id),
        "title": e.title,
        "description": e.description,
        "start_time": e.start_time.isoformat(),
        "end_time": e.end_time.isoformat() if e.end_time else None,
        "location": e.location,
        "recurring": e.recurring,
        "created_at": e.created_at.isoformat(),
    }

"""Calendar service — CRUD for events and schedule context."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from sqlalchemy import select, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import user_today
from app.db.models import CalendarEventRow


async def create_event(
    session: AsyncSession,
    title: str,
    start_time: datetime,
    end_time: Optional[datetime] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
    recurring: Optional[str] = None,
    *,
    user_id: uuid.UUID,
) -> CalendarEventRow:
    row = CalendarEventRow(
        user_id=user_id,
        title=title,
        description=description,
        start_time=start_time,
        end_time=end_time,
        location=location,
        recurring=recurring,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def get_events(
    session: AsyncSession,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    *,
    user_id: uuid.UUID,
) -> list[CalendarEventRow]:
    q = select(CalendarEventRow).where(CalendarEventRow.user_id == user_id)
    if start_date:
        q = q.where(CalendarEventRow.start_time >= datetime.combine(start_date, time.min).replace(tzinfo=timezone.utc))
    if end_date:
        q = q.where(CalendarEventRow.start_time <= datetime.combine(end_date, time.max).replace(tzinfo=timezone.utc))
    q = q.order_by(CalendarEventRow.start_time.asc())
    result = await session.execute(q)
    return list(result.scalars().all())


async def get_today_events(session: AsyncSession, *, user_id: uuid.UUID) -> list[CalendarEventRow]:
    today = user_today()
    return await get_events(session, start_date=today, end_date=today, user_id=user_id)


async def get_event(session: AsyncSession, event_id: uuid.UUID) -> Optional[CalendarEventRow]:
    return await session.get(CalendarEventRow, event_id)


async def update_event(session: AsyncSession, event_id: uuid.UUID, **fields) -> Optional[CalendarEventRow]:
    row = await session.get(CalendarEventRow, event_id)
    if not row:
        return None
    for key, value in fields.items():
        if value is not None and hasattr(row, key):
            setattr(row, key, value)
    await session.commit()
    await session.refresh(row)
    return row


async def delete_event(session: AsyncSession, event_id: uuid.UUID) -> bool:
    result = await session.execute(delete(CalendarEventRow).where(CalendarEventRow.id == event_id))
    await session.commit()
    return result.rowcount > 0


async def get_schedule_context(session: AsyncSession, *, user_id: uuid.UUID) -> str:
    """Build schedule context string for chat prompt."""
    events = await get_today_events(session, user_id=user_id)
    if not events:
        return ""
    lines = []
    for e in events:
        t = e.start_time.strftime("%I:%M %p")
        end = f" - {e.end_time.strftime('%I:%M %p')}" if e.end_time else ""
        loc = f" @ {e.location}" if e.location else ""
        lines.append(f"- {t}{end}: {e.title}{loc}")
    return "\n".join(lines)

"""Knowledge base service — query and manage stored facts."""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select, delete, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import KnowledgeRow


async def get_knowledge(
    session: AsyncSession,
    category: Optional[str] = None,
    search: Optional[str] = None,
    *,
    user_id: uuid.UUID,
) -> list[KnowledgeRow]:
    q = select(KnowledgeRow).where(KnowledgeRow.user_id == user_id)
    if category:
        q = q.where(KnowledgeRow.category == category)
    if search:
        q = q.where(KnowledgeRow.content.ilike(f"%{search}%"))
    q = q.order_by(KnowledgeRow.created_at.desc())
    result = await session.execute(q)
    return list(result.scalars().all())


async def get_knowledge_entry(session: AsyncSession, entry_id: uuid.UUID) -> Optional[KnowledgeRow]:
    return await session.get(KnowledgeRow, entry_id)


async def delete_knowledge(session: AsyncSession, entry_id: uuid.UUID) -> bool:
    result = await session.execute(delete(KnowledgeRow).where(KnowledgeRow.id == entry_id))
    await session.commit()
    return result.rowcount > 0

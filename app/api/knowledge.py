"""Knowledge API — list, get, delete stored facts and preferences."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.engine import get_db
from app.services import knowledge_service

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get("")
async def list_knowledge(
    category: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user),
):
    entries = await knowledge_service.get_knowledge(db, category=category, search=search, user_id=user_id)
    return {
        "entries": [_entry_response(e) for e in entries],
        "count": len(entries),
    }


@router.get("/{entry_id}")
async def get_knowledge(entry_id: uuid.UUID, db: AsyncSession = Depends(get_db), user_id: uuid.UUID = Depends(get_current_user)):
    entry = await knowledge_service.get_knowledge_entry(db, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Knowledge entry not found")
    return _entry_response(entry)


@router.delete("/{entry_id}")
async def delete_knowledge(entry_id: uuid.UUID, db: AsyncSession = Depends(get_db), user_id: uuid.UUID = Depends(get_current_user)):
    deleted = await knowledge_service.delete_knowledge(db, entry_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Knowledge entry not found")
    return {"deleted": True}


def _entry_response(e) -> dict:
    return {
        "id": str(e.id),
        "category": e.category,
        "content": e.content,
        "tags": e.tags,
        "source_message_id": str(e.source_message_id) if e.source_message_id else None,
        "created_at": e.created_at.isoformat(),
    }

"""Grocery Lists API — create, list, get, toggle item, delete."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.engine import get_db
from app.services import recipe_service

router = APIRouter(prefix="/grocery-lists", tags=["grocery"])


class CreateGroceryListRequest(BaseModel):
    name: str = "Grocery List"
    items: list[dict] = Field(default_factory=list)


@router.post("", status_code=201)
async def create_grocery_list(body: CreateGroceryListRequest, db: AsyncSession = Depends(get_db), user_id: uuid.UUID = Depends(get_current_user)):
    gl = await recipe_service.create_grocery_list(db, name=body.name, items=body.items, user_id=user_id)
    return _gl_response(gl)


@router.get("")
async def list_grocery_lists(db: AsyncSession = Depends(get_db), user_id: uuid.UUID = Depends(get_current_user)):
    lists = await recipe_service.get_grocery_lists(db, user_id=user_id)
    return {"lists": [_gl_response(gl) for gl in lists], "count": len(lists)}


@router.get("/{list_id}")
async def get_grocery_list(list_id: uuid.UUID, db: AsyncSession = Depends(get_db), user_id: uuid.UUID = Depends(get_current_user)):
    gl = await recipe_service.get_grocery_list(db, list_id, user_id=user_id)
    if not gl:
        raise HTTPException(status_code=404, detail="Grocery list not found")
    return _gl_response(gl)


@router.patch("/{list_id}/items/{item_idx}/check")
async def toggle_item(list_id: uuid.UUID, item_idx: int, db: AsyncSession = Depends(get_db), user_id: uuid.UUID = Depends(get_current_user)):
    gl = await recipe_service.toggle_grocery_item(db, list_id, item_idx, user_id=user_id)
    if not gl:
        raise HTTPException(status_code=404, detail="List or item not found")
    return _gl_response(gl)


@router.delete("/{list_id}")
async def delete_grocery_list(list_id: uuid.UUID, db: AsyncSession = Depends(get_db), user_id: uuid.UUID = Depends(get_current_user)):
    deleted = await recipe_service.delete_grocery_list(db, list_id, user_id=user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Grocery list not found")
    return {"deleted": True}


def _gl_response(gl) -> dict:
    return {
        "id": str(gl.id),
        "name": gl.name,
        "items": gl.items,
        "created_at": gl.created_at.isoformat(),
    }

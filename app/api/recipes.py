"""Recipes API — create, list, get, delete recipes."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.engine import get_db
from app.services import recipe_service

router = APIRouter(prefix="/recipes", tags=["recipes"])


class CreateRecipeRequest(BaseModel):
    name: str = Field(..., min_length=1)
    ingredients: list[dict] = Field(...)
    instructions: str = Field(..., min_length=1)
    calories: float = 0
    protein_g: float = 0
    prep_time_minutes: Optional[int] = None
    tags: Optional[list[str]] = None


@router.post("", status_code=201)
async def create_recipe(body: CreateRecipeRequest, db: AsyncSession = Depends(get_db), user_id: uuid.UUID = Depends(get_current_user)):
    recipe = await recipe_service.create_recipe(
        db, name=body.name, ingredients=body.ingredients,
        instructions=body.instructions, calories=body.calories,
        protein_g=body.protein_g, prep_time_minutes=body.prep_time_minutes,
        tags=body.tags, user_id=user_id,
    )
    return _recipe_response(recipe)


@router.get("")
async def list_recipes(
    search: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user),
):
    recipes = await recipe_service.get_recipes(db, search=search, user_id=user_id)
    return {"recipes": [_recipe_response(r) for r in recipes], "count": len(recipes)}


@router.get("/{recipe_id}")
async def get_recipe(recipe_id: uuid.UUID, db: AsyncSession = Depends(get_db), user_id: uuid.UUID = Depends(get_current_user)):
    recipe = await recipe_service.get_recipe(db, recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return _recipe_response(recipe)


@router.delete("/{recipe_id}")
async def delete_recipe(recipe_id: uuid.UUID, db: AsyncSession = Depends(get_db), user_id: uuid.UUID = Depends(get_current_user)):
    deleted = await recipe_service.delete_recipe(db, recipe_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return {"deleted": True}


def _recipe_response(r) -> dict:
    return {
        "id": str(r.id),
        "name": r.name,
        "ingredients": r.ingredients,
        "instructions": r.instructions,
        "calories": r.calories,
        "protein_g": r.protein_g,
        "prep_time_minutes": r.prep_time_minutes,
        "tags": r.tags,
        "created_at": r.created_at.isoformat(),
    }

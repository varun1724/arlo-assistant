"""Recipe and Grocery List service."""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import RecipeRow, GroceryListRow


# ─── Recipes ────────────────────────────────────────────

async def create_recipe(
    session: AsyncSession,
    name: str,
    ingredients: list[dict],
    instructions: str,
    calories: float = 0,
    protein_g: float = 0,
    prep_time_minutes: Optional[int] = None,
    tags: Optional[list[str]] = None,
    *,
    user_id: uuid.UUID,
) -> RecipeRow:
    row = RecipeRow(
        user_id=user_id,
        name=name,
        ingredients=ingredients,
        instructions=instructions,
        calories=calories,
        protein_g=protein_g,
        prep_time_minutes=prep_time_minutes,
        tags=tags,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def get_recipes(
    session: AsyncSession,
    search: Optional[str] = None,
    *,
    user_id: uuid.UUID,
) -> list[RecipeRow]:
    q = select(RecipeRow).where(RecipeRow.user_id == user_id)
    if search:
        q = q.where(RecipeRow.name.ilike(f"%{search}%"))
    q = q.order_by(RecipeRow.created_at.desc())
    result = await session.execute(q)
    return list(result.scalars().all())


async def get_recipe(
    session: AsyncSession, recipe_id: uuid.UUID, *, user_id: uuid.UUID,
) -> Optional[RecipeRow]:
    row = await session.get(RecipeRow, recipe_id)
    if row is None or row.user_id != user_id:
        return None
    return row


async def delete_recipe(
    session: AsyncSession, recipe_id: uuid.UUID, *, user_id: uuid.UUID,
) -> bool:
    result = await session.execute(
        delete(RecipeRow).where(RecipeRow.id == recipe_id, RecipeRow.user_id == user_id)
    )
    await session.commit()
    return result.rowcount > 0


# ─── Grocery Lists ──────────────────────────────────────

async def create_grocery_list(
    session: AsyncSession,
    name: str = "Grocery List",
    items: list[dict] = None,
    *,
    user_id: uuid.UUID,
) -> GroceryListRow:
    row = GroceryListRow(
        user_id=user_id,
        name=name,
        items=items or [],
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def get_grocery_lists(session: AsyncSession, *, user_id: uuid.UUID) -> list[GroceryListRow]:
    result = await session.execute(
        select(GroceryListRow)
        .where(GroceryListRow.user_id == user_id)
        .order_by(GroceryListRow.created_at.desc())
    )
    return list(result.scalars().all())


async def get_grocery_list(
    session: AsyncSession, list_id: uuid.UUID, *, user_id: uuid.UUID,
) -> Optional[GroceryListRow]:
    row = await session.get(GroceryListRow, list_id)
    if row is None or row.user_id != user_id:
        return None
    return row


async def toggle_grocery_item(
    session: AsyncSession, list_id: uuid.UUID, item_idx: int, *, user_id: uuid.UUID,
) -> Optional[GroceryListRow]:
    row = await session.get(GroceryListRow, list_id)
    if row is None or row.user_id != user_id or not row.items:
        return None
    if item_idx < 0 or item_idx >= len(row.items):
        return None
    from sqlalchemy.orm.attributes import flag_modified
    items = [dict(i) for i in row.items]  # deep copy for mutation
    items[item_idx]["checked"] = not items[item_idx].get("checked", False)
    row.items = items
    flag_modified(row, "items")
    await session.commit()
    await session.refresh(row)
    return row


async def delete_grocery_list(
    session: AsyncSession, list_id: uuid.UUID, *, user_id: uuid.UUID,
) -> bool:
    result = await session.execute(
        delete(GroceryListRow).where(
            GroceryListRow.id == list_id, GroceryListRow.user_id == user_id,
        )
    )
    await session.commit()
    return result.rowcount > 0

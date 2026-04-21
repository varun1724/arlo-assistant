"""Auth API — register, login, refresh, me."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user, verify_refresh_token
from app.db.engine import get_db
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=6)
    name: str = "User"


class LoginRequest(BaseModel):
    email: str = Field(...)
    password: str = Field(...)


@router.post("/register", status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    try:
        user, tokens = await auth_service.register(db, email=body.email, password=body.password, name=body.name)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {
        "user": {"id": str(user.id), "name": user.name, "email": body.email},
        **tokens,
    }


@router.post("/login")
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    try:
        user, tokens = await auth_service.login(db, email=body.email, password=body.password)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    return {
        "user": {"id": str(user.id), "name": user.name},
        **tokens,
    }


@router.post("/refresh")
async def refresh(user_id=Depends(verify_refresh_token), db: AsyncSession = Depends(get_db)):
    user = await auth_service.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    tokens = auth_service.create_tokens(user_id)
    return tokens


@router.get("/me")
async def me(user_id=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.db.models import AuthUserRow
    user = await auth_service.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    auth_user = await db.get(AuthUserRow, user_id)
    email = auth_user.email if auth_user else None
    return {"id": str(user.id), "name": user.name, "email": email}

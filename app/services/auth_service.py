"""Auth service — user registration, login, token management."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from jose import jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import AuthUserRow, UserRow
from app.services import reminder_service

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(user_id: uuid.UUID) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_access_expiry_minutes)
    payload = {"sub": str(user_id), "exp": expire, "type": "access"}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def create_refresh_token(user_id: uuid.UUID) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_expiry_days)
    payload = {"sub": str(user_id), "exp": expire, "type": "refresh"}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def create_tokens(user_id: uuid.UUID) -> dict:
    return {
        "access_token": create_access_token(user_id),
        "refresh_token": create_refresh_token(user_id),
        "token_type": "bearer",
    }


async def register(session: AsyncSession, email: str, password: str, name: str = "User") -> tuple[UserRow, dict]:
    """Register a new user. Returns (user, tokens)."""
    # Check email not taken
    existing = await session.execute(select(AuthUserRow).where(AuthUserRow.email == email))
    if existing.scalars().first():
        raise ValueError("Email already registered")

    # Create user + auth records
    user = UserRow(name=name)
    session.add(user)
    await session.flush()  # get user.id

    auth_user = AuthUserRow(id=user.id, email=email, password_hash=hash_password(password))
    session.add(auth_user)
    await session.commit()
    await session.refresh(user)

    # Seed default daily reminders for new user
    await reminder_service.seed_default_reminders(session, user_id=user.id)

    return user, create_tokens(user.id)


async def login(session: AsyncSession, email: str, password: str) -> tuple[UserRow, dict]:
    """Authenticate user. Returns (user, tokens)."""
    result = await session.execute(select(AuthUserRow).where(AuthUserRow.email == email))
    auth_user = result.scalars().first()

    if not auth_user or not verify_password(password, auth_user.password_hash):
        raise ValueError("Invalid email or password")

    if not auth_user.is_active:
        raise ValueError("Account is deactivated")

    user = await session.get(UserRow, auth_user.id)
    return user, create_tokens(auth_user.id)


async def get_user_by_id(session: AsyncSession, user_id: uuid.UUID) -> UserRow | None:
    return await session.get(UserRow, user_id)

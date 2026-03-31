"""Chat API — async conversational interface."""

from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_token
from app.db.engine import get_db, async_session
from app.services import chat_service

router = APIRouter(prefix="/chat", tags=["chat"], dependencies=[Depends(verify_token)])


class SendMessageRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=10000)
    conversation_id: uuid.UUID | None = None


class MessageResponse(BaseModel):
    message_id: uuid.UUID
    conversation_id: uuid.UUID
    status: str
    content: str


@router.post("/message", response_model=MessageResponse)
async def send_message(
    body: SendMessageRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Send a message. Returns immediately with a message_id.
    The response is processed in the background.
    Poll GET /chat/message/{id} for the response.
    """
    conversation_id, message_id = await chat_service.send_message(
        db, body.conversation_id, body.text,
    )

    # Process in background so the user isn't blocked
    background_tasks.add_task(_process_in_background, message_id)

    return MessageResponse(
        message_id=message_id,
        conversation_id=conversation_id,
        status="thinking",
        content="",
    )


async def _process_in_background(message_id: uuid.UUID):
    """Process the message using a fresh DB session."""
    async with async_session() as session:
        await chat_service.process_message(session, message_id)


@router.get("/message/{message_id}", response_model=MessageResponse)
async def get_message(
    message_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a message by ID. Check status: 'thinking' means still processing."""
    msg = await chat_service.get_message(db, message_id)
    if msg is None:
        raise HTTPException(status_code=404, detail="Message not found")
    return MessageResponse(
        message_id=msg.id,
        conversation_id=msg.conversation_id,
        status=msg.status,
        content=msg.content,
    )


@router.get("/conversations")
async def list_conversations(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    convos = await chat_service.get_conversations(db, limit=limit)
    return {
        "conversations": [
            {
                "id": str(c.id),
                "title": c.title,
                "created_at": c.created_at.isoformat(),
                "updated_at": c.updated_at.isoformat(),
            }
            for c in convos
        ],
        "count": len(convos),
    }


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    messages = await chat_service.get_conversation_messages(db, conversation_id)
    return {
        "conversation_id": str(conversation_id),
        "messages": [
            {
                "id": str(m.id),
                "role": m.role,
                "content": m.content,
                "status": m.status,
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ],
        "count": len(messages),
    }

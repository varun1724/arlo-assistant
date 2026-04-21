"""Chat API — async conversational interface with SSE support."""

import asyncio
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.core.security import get_current_user
from app.db.engine import get_db, async_session
from app.services import chat_service

router = APIRouter(prefix="/chat", tags=["chat"])


class SendMessageRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=10000)
    conversation_id: uuid.UUID | None = None  # noqa: UP007 - Pydantic needs runtime type


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
    user_id: uuid.UUID = Depends(get_current_user),
):
    """Send a message. Returns immediately with a message_id.
    The response is processed in the background.
    Poll GET /chat/message/{id} for the response.
    """
    conversation_id, message_id = await chat_service.send_message(
        db, body.conversation_id, body.text, user_id=user_id,
    )

    # Process in background so the user isn't blocked
    background_tasks.add_task(_process_in_background, message_id, user_id)

    return MessageResponse(
        message_id=message_id,
        conversation_id=conversation_id,
        status="thinking",
        content="",
    )


async def _process_in_background(message_id: uuid.UUID, user_id: uuid.UUID):
    """Process the message using a fresh DB session."""
    async with async_session() as session:
        await chat_service.process_message(session, message_id, user_id=user_id)


@router.get("/message/{message_id}", response_model=MessageResponse)
async def get_message(
    message_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user),
):
    """Get a message by ID. Check status: 'thinking' means still processing."""
    msg = await chat_service.get_message(db, message_id, user_id=user_id)
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
    user_id: uuid.UUID = Depends(get_current_user),
):
    convos = await chat_service.get_conversations(db, limit=limit, user_id=user_id)
    out = []
    for c in convos:
        last = await chat_service.get_last_message(db, c.id)
        preview = None
        role = None
        if last is not None:
            preview = (last.content or "")[:160]
            role = last.role
        out.append({
            "id": str(c.id),
            "title": c.title,
            "created_at": c.created_at.isoformat(),
            "updated_at": c.updated_at.isoformat(),
            "last_message_preview": preview,
            "last_message_role": role,
        })
    return {"conversations": out, "count": len(convos)}


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user),
):
    ok = await chat_service.delete_conversation(db, conversation_id, user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"deleted": True}


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user),
):
    messages = await chat_service.get_conversation_messages(
        db, conversation_id, user_id=user_id,
    )
    if messages is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
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


@router.get("/message/{message_id}/stream")
async def stream_message(
    message_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user),
):
    """SSE stream that pushes updates until the message is complete.
    Use this instead of polling GET /chat/message/{id}.
    """
    # Verify ownership once before the stream opens, so an unauthorized caller
    # gets an immediate 404 instead of an event stream that silently emits
    # another user's content.
    async with async_session() as session:
        initial = await chat_service.get_message(session, message_id, user_id=user_id)
    if initial is None:
        raise HTTPException(status_code=404, detail="Message not found")

    async def event_generator():
        import json
        async with async_session() as session:
            while True:
                msg = await chat_service.get_message(session, message_id)
                if msg is None:
                    yield {"event": "error", "data": json.dumps({"error": "Message not found"})}
                    return
                data = {
                    "message_id": str(msg.id),
                    "status": msg.status,
                    "content": msg.content,
                }
                yield {"event": "message", "data": json.dumps(data)}
                if msg.status in ("complete", "error"):
                    return
                await asyncio.sleep(1)
                await session.expire_all()

    return EventSourceResponse(event_generator())

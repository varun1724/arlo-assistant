"""Chat service — manages conversations and coordinates with Claude."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ConversationRow, MessageRow, UserProfileRow, HealthDailyRow, TaskRow
from app.llm.claude import chat_with_claude, ClaudeError
from app.llm.prompts import build_system_prompt
from app.llm.extractors import extract_actions

logger = logging.getLogger("arlo.assistant.chat")

# Default user ID (single-user for now)
DEFAULT_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


async def send_message(
    session: AsyncSession,
    conversation_id: uuid.UUID | None,
    user_text: str,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Create a user message and queue an assistant response.

    Returns (conversation_id, message_id) for the assistant's response.
    The response is processed asynchronously.
    """
    # Get or create conversation
    if conversation_id is None:
        conv = ConversationRow(user_id=DEFAULT_USER_ID, title=user_text[:100])
        session.add(conv)
        await session.commit()
        await session.refresh(conv)
        conversation_id = conv.id

    # Save user message
    user_msg = MessageRow(
        conversation_id=conversation_id,
        role="user",
        content=user_text,
        status="complete",
    )
    session.add(user_msg)

    # Create placeholder for assistant response
    assistant_msg = MessageRow(
        conversation_id=conversation_id,
        role="assistant",
        content="",
        status="thinking",
    )
    session.add(assistant_msg)
    await session.commit()
    await session.refresh(assistant_msg)

    return conversation_id, assistant_msg.id


async def process_message(
    session: AsyncSession,
    message_id: uuid.UUID,
) -> None:
    """Process a pending assistant message — build context, call Claude, extract actions."""
    msg = await session.get(MessageRow, message_id)
    if msg is None or msg.status != "thinking":
        return

    try:
        # Build context
        profile_summary = await _get_profile_summary(session)
        health_today = await _get_health_today(session)
        pending_tasks = await _get_pending_tasks(session)
        recent_messages = await _get_recent_messages(session, msg.conversation_id)

        system_prompt = build_system_prompt(
            profile_summary, health_today, pending_tasks, recent_messages,
        )

        # Get the user's message (the one before this assistant message)
        result = await session.execute(
            select(MessageRow)
            .where(
                MessageRow.conversation_id == msg.conversation_id,
                MessageRow.role == "user",
            )
            .order_by(MessageRow.created_at.desc())
            .limit(1)
        )
        user_msg = result.scalars().first()
        user_text = user_msg.content if user_msg else ""

        # Call Claude
        response = await chat_with_claude(user_text, system_prompt=system_prompt)

        # Extract actions
        clean_text, actions = extract_actions(response)

        # Process actions
        await _process_actions(session, actions)

        # Update message
        await session.execute(
            update(MessageRow)
            .where(MessageRow.id == message_id)
            .values(
                content=clean_text,
                status="complete",
                metadata_json={"actions": actions} if actions else None,
            )
        )
        await session.commit()
        logger.info("Message %s processed successfully (%d actions)", message_id, len(actions))

    except ClaudeError as e:
        await session.execute(
            update(MessageRow)
            .where(MessageRow.id == message_id)
            .values(content=f"Sorry, I had trouble processing that: {e}", status="error")
        )
        await session.commit()
        logger.error("Message %s failed: %s", message_id, e)

    except Exception as e:
        await session.execute(
            update(MessageRow)
            .where(MessageRow.id == message_id)
            .values(content=f"Something went wrong: {e}", status="error")
        )
        await session.commit()
        logger.exception("Message %s failed unexpectedly", message_id)


async def get_message(session: AsyncSession, message_id: uuid.UUID) -> MessageRow | None:
    return await session.get(MessageRow, message_id)


async def get_conversations(session: AsyncSession, limit: int = 20) -> list[ConversationRow]:
    result = await session.execute(
        select(ConversationRow)
        .where(ConversationRow.user_id == DEFAULT_USER_ID)
        .order_by(ConversationRow.updated_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_conversation_messages(
    session: AsyncSession, conversation_id: uuid.UUID, limit: int = 50
) -> list[MessageRow]:
    result = await session.execute(
        select(MessageRow)
        .where(MessageRow.conversation_id == conversation_id)
        .order_by(MessageRow.created_at.asc())
        .limit(limit)
    )
    return list(result.scalars().all())


# ─── Private helpers ─────────────────────────────────────

async def _get_profile_summary(session: AsyncSession) -> str:
    result = await session.execute(
        select(UserProfileRow)
        .where(UserProfileRow.user_id == DEFAULT_USER_ID)
        .order_by(UserProfileRow.updated_at.desc())
        .limit(50)
    )
    rows = result.scalars().all()
    if not rows:
        return ""
    lines = [f"- {r.category}/{r.key}: {r.value}" for r in rows]
    return "\n".join(lines)


async def _get_health_today(session: AsyncSession) -> str:
    from datetime import date
    today = date.today()
    result = await session.execute(
        select(HealthDailyRow)
        .where(HealthDailyRow.user_id == DEFAULT_USER_ID, HealthDailyRow.date == today)
    )
    row = result.scalars().first()
    if not row:
        return ""
    return (
        f"Steps: {row.steps}, Calories: {row.calories}, "
        f"Protein: {row.protein_g}g, Carbs: {row.carbs_g}g, Fat: {row.fat_g}g, "
        f"Water: {row.water_oz}oz"
    )


async def _get_pending_tasks(session: AsyncSession) -> str:
    result = await session.execute(
        select(TaskRow)
        .where(TaskRow.user_id == DEFAULT_USER_ID, TaskRow.status == "todo")
        .order_by(TaskRow.priority.desc())
        .limit(10)
    )
    rows = result.scalars().all()
    if not rows:
        return ""
    lines = [f"- [{r.priority}] {r.title}" + (f" (due {r.due_date})" if r.due_date else "") for r in rows]
    return "\n".join(lines)


async def _get_recent_messages(session: AsyncSession, conversation_id: uuid.UUID) -> str:
    result = await session.execute(
        select(MessageRow)
        .where(MessageRow.conversation_id == conversation_id, MessageRow.status == "complete")
        .order_by(MessageRow.created_at.desc())
        .limit(10)
    )
    rows = list(result.scalars().all())
    rows.reverse()  # chronological order
    if not rows:
        return ""
    lines = [f"{r.role}: {r.content[:300]}" for r in rows]
    return "\n".join(lines)


async def _process_actions(session: AsyncSession, actions: list[dict]) -> None:
    """Execute extracted actions from Claude's response."""
    for action in actions:
        action_type = action.get("type", "")
        try:
            if action_type == "profile_update":
                row = UserProfileRow(
                    user_id=DEFAULT_USER_ID,
                    category=action.get("category", "general"),
                    key=action.get("key", ""),
                    value=str(action.get("value", "")),
                    source="chat",
                )
                session.add(row)

            elif action_type == "log_meal":
                from datetime import date
                row = __import__("app.db.models", fromlist=["MealRow"]).MealRow(
                    user_id=DEFAULT_USER_ID,
                    date=date.today(),
                    description=action.get("description", ""),
                    calories=action.get("calories", 0),
                    protein_g=action.get("protein_g", 0),
                    carbs_g=action.get("carbs_g", 0),
                    fat_g=action.get("fat_g", 0),
                )
                session.add(row)

            elif action_type == "create_task":
                from app.db.models import TaskRow as TR
                row = TR(
                    user_id=DEFAULT_USER_ID,
                    title=action.get("title", ""),
                    priority=action.get("priority", "medium"),
                )
                if action.get("due_date"):
                    from datetime import date
                    row.due_date = date.fromisoformat(action["due_date"])
                session.add(row)

            elif action_type == "save_knowledge":
                from app.db.models import KnowledgeRow
                row = KnowledgeRow(
                    user_id=DEFAULT_USER_ID,
                    category=action.get("category", "fact"),
                    content=action.get("content", ""),
                )
                session.add(row)

            elif action_type == "create_reminder":
                from app.db.models import ReminderRow
                row = ReminderRow(
                    user_id=DEFAULT_USER_ID,
                    message=action.get("message", ""),
                    smart_condition=action.get("smart_condition"),
                )
                session.add(row)

        except Exception as e:
            logger.warning("Failed to process action %s: %s", action_type, e)

    await session.commit()

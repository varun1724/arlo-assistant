"""Chat service — manages conversations and coordinates with Claude."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ConversationRow, MessageRow, UserProfileRow, HealthDailyRow, MealRow, TaskRow, GoalRow, GroceryListRow, RecipeRow
from app.llm.claude import chat_with_claude, ClaudeError
from app.llm.prompts import build_system_prompt
from app.llm.extractors import extract_actions

logger = logging.getLogger("arlo.assistant.chat")

# Legacy default user ID — used only as a fallback default parameter
DEFAULT_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


from app.core.time import user_today as _user_today  # noqa: E402 — keep import local-feeling


async def send_message(
    session: AsyncSession,
    conversation_id: uuid.UUID | None,
    user_text: str,
    user_id: uuid.UUID = DEFAULT_USER_ID,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Create a user message and queue an assistant response.

    Returns (conversation_id, message_id) for the assistant's response.
    The response is processed asynchronously.
    """
    # Get or create conversation
    if conversation_id is None:
        conv = ConversationRow(user_id=user_id, title=user_text[:100])
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
    user_id: uuid.UUID = DEFAULT_USER_ID,
) -> None:
    """Process a pending assistant message — build context, call Claude, extract actions."""
    msg = await session.get(MessageRow, message_id)
    if msg is None or msg.status != "thinking":
        return

    try:
        # Build context
        profile_summary = await _get_profile_summary(session, user_id)
        health_today = await _get_health_today(session, user_id)
        pending_tasks = await _get_pending_tasks(session, user_id)
        recent_messages = await _get_recent_messages(session, msg.conversation_id)
        triggered_reminders = await _get_triggered_reminders(session, user_id)
        weather = await _get_weather()
        schedule = await _get_schedule(session, user_id)
        goals_context = await _get_goals_context(session, user_id)
        grocery_context = await _get_grocery_context(session, user_id)
        recipe_context = await _get_recipe_context(session, user_id)

        system_prompt = build_system_prompt(
            profile_summary, health_today, pending_tasks, recent_messages,
            triggered_reminders=triggered_reminders,
            weather=weather,
            schedule=schedule,
            goals_context=goals_context,
            grocery_context=grocery_context,
            recipe_context=recipe_context,
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
        await _process_actions(session, actions, user_id)

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


async def get_conversations(session: AsyncSession, limit: int = 20, user_id: uuid.UUID = DEFAULT_USER_ID) -> list[ConversationRow]:
    result = await session.execute(
        select(ConversationRow)
        .where(ConversationRow.user_id == user_id)
        .order_by(ConversationRow.updated_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_last_message(
    session: AsyncSession, conversation_id: uuid.UUID
) -> MessageRow | None:
    """Return the most recent complete message in a conversation, for list previews."""
    result = await session.execute(
        select(MessageRow)
        .where(
            MessageRow.conversation_id == conversation_id,
            MessageRow.status == "complete",
        )
        .order_by(MessageRow.created_at.desc())
        .limit(1)
    )
    return result.scalars().first()


async def delete_conversation(
    session: AsyncSession, conversation_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    """Delete a conversation and all of its messages. Returns True if deleted."""
    from sqlalchemy import delete
    # Only allow deleting conversations owned by this user.
    convo = await session.get(ConversationRow, conversation_id)
    if convo is None or convo.user_id != user_id:
        return False
    await session.execute(
        delete(MessageRow).where(MessageRow.conversation_id == conversation_id)
    )
    await session.execute(
        delete(ConversationRow).where(ConversationRow.id == conversation_id)
    )
    await session.commit()
    return True


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

async def _get_profile_summary(session: AsyncSession, user_id: uuid.UUID) -> str:
    result = await session.execute(
        select(UserProfileRow)
        .where(UserProfileRow.user_id == user_id)
        .order_by(UserProfileRow.updated_at.desc())
        .limit(50)
    )
    rows = result.scalars().all()
    if not rows:
        return ""
    lines = [f"- {r.category}/{r.key}: {r.value}" for r in rows]
    return "\n".join(lines)


async def _get_health_today(session: AsyncSession, user_id: uuid.UUID) -> str:
    today = _user_today()

    # Activity totals (steps, active calories, sleep, heart rate)
    daily_result = await session.execute(
        select(HealthDailyRow)
        .where(HealthDailyRow.user_id == user_id, HealthDailyRow.date == today)
    )
    daily = daily_result.scalars().first()

    # Today's logged meals (authoritative source for nutrition data)
    meals_result = await session.execute(
        select(MealRow)
        .where(MealRow.user_id == user_id, MealRow.date == today)
        .order_by(MealRow.created_at.asc())
    )
    meals = meals_result.scalars().all()

    lines = []
    if daily and daily.steps:
        lines.append(f"Steps: {daily.steps}")
    if daily and daily.sleep_hours:
        lines.append(f"Sleep: {daily.sleep_hours}h")
    if daily and daily.resting_heart_rate:
        lines.append(f"Resting HR: {daily.resting_heart_rate} bpm")

    if meals:
        total_cal = sum(m.calories for m in meals)
        total_prot = sum(m.protein_g for m in meals)
        total_carbs = sum(m.carbs_g for m in meals)
        total_fat = sum(m.fat_g for m in meals)
        lines.append(
            f"Nutrition logged: {total_cal:.0f} kcal, "
            f"{total_prot:.0f}g protein, {total_carbs:.0f}g carbs, {total_fat:.0f}g fat"
        )
        meal_lines = [
            f"  - {m.meal_type.capitalize()}: {m.description} "
            f"({m.calories:.0f} kcal, {m.protein_g:.0f}g P)"
            for m in meals
        ]
        lines.extend(meal_lines)
    else:
        lines.append("No meals logged yet today.")

    return "\n".join(lines) if lines else ""


async def _get_pending_tasks(session: AsyncSession, user_id: uuid.UUID) -> str:
    result = await session.execute(
        select(TaskRow)
        .where(TaskRow.user_id == user_id, TaskRow.status == "todo")
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


async def _get_triggered_reminders(session: AsyncSession, user_id: uuid.UUID) -> str:
    from app.services.reminder_service import get_triggered_reminders
    triggered = await get_triggered_reminders(session, user_id=user_id)
    if not triggered:
        return ""
    lines = [f"- {r.message}" for r in triggered]
    return "\n".join(lines)


async def _get_weather() -> str:
    from app.services.weather_service import get_weather_context
    return await get_weather_context()


async def _get_schedule(session: AsyncSession, user_id: uuid.UUID) -> str:
    from app.services.calendar_service import get_schedule_context
    return await get_schedule_context(session, user_id=user_id)


async def _get_goals_context(session: AsyncSession, user_id: uuid.UUID) -> str:
    from datetime import date
    from sqlalchemy import func as sqlfunc
    today = date.today()
    result = await session.execute(
        select(GoalRow).where(GoalRow.user_id == user_id, GoalRow.status == "active")
    )
    goals = result.scalars().all()

    # Sum macros directly from MealRow — accurate regardless of how meals were logged
    macro_result = await session.execute(
        select(
            sqlfunc.coalesce(sqlfunc.sum(MealRow.protein_g), 0),
            sqlfunc.coalesce(sqlfunc.sum(MealRow.calories), 0),
        ).where(MealRow.user_id == user_id, MealRow.date == today)
    )
    totals = macro_result.one()
    logged_protein = float(totals[0])
    logged_calories = float(totals[1])

    lines = []
    for g in goals:
        lines.append(f"- {g.title}: {g.target_value}{g.unit} (current: {g.current_value})")

    lines.append(f"- Protein today: {logged_protein:.0f}g logged, {max(0, 200 - logged_protein):.0f}g remaining to hit 200g target")
    lines.append(f"- Calories today: {logged_calories:.0f} kcal logged, {max(0, 3000 - logged_calories):.0f} kcal remaining to hit 3000 kcal target")
    return "\n".join(lines) if lines else ""


async def _get_grocery_context(session: AsyncSession, user_id: uuid.UUID) -> str:
    result = await session.execute(
        select(GroceryListRow).where(GroceryListRow.user_id == user_id).limit(1)
    )
    grocery = result.scalars().first()
    if not grocery or not grocery.items:
        return ""
    unchecked = [
        item.get("item", "") for item in grocery.items
        if not item.get("checked", False) and item.get("item")
    ][:12]
    return ", ".join(unchecked) if unchecked else ""


async def _get_recipe_context(session: AsyncSession, user_id: uuid.UUID) -> str:
    result = await session.execute(
        select(RecipeRow).where(RecipeRow.user_id == user_id).limit(6)
    )
    recipes = result.scalars().all()
    if not recipes:
        return ""
    lines = [f"{r.name} ({int(r.protein_g)}g P, {int(r.calories)} kcal)" for r in recipes]
    return ", ".join(lines)


async def _process_actions(session: AsyncSession, actions: list[dict], user_id: uuid.UUID) -> None:
    """Execute extracted actions from Claude's response."""
    for action in actions:
        action_type = action.get("type", "")
        try:
            if action_type == "profile_update":
                row = UserProfileRow(
                    user_id=user_id,
                    category=action.get("category", "general"),
                    key=action.get("key", ""),
                    value=str(action.get("value", "")),
                    source="chat",
                )
                session.add(row)

            elif action_type == "log_meal":
                from app.services.health_service import log_meal as _log_meal
                desc = action.get("description", "").strip()
                if desc:
                    await _log_meal(
                        session,
                        description=desc,
                        calories=action.get("calories", 0),
                        protein_g=action.get("protein_g", 0),
                        carbs_g=action.get("carbs_g", 0),
                        fat_g=action.get("fat_g", 0),
                        meal_type=action.get("meal_type", "other"),
                        user_id=user_id,
                    )

            elif action_type == "create_task":
                from app.db.models import TaskRow as TR
                row = TR(
                    user_id=user_id,
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
                    user_id=user_id,
                    category=action.get("category", "fact"),
                    content=action.get("content", ""),
                )
                session.add(row)

            elif action_type == "create_reminder":
                from app.db.models import ReminderRow
                row = ReminderRow(
                    user_id=user_id,
                    message=action.get("message", ""),
                    smart_condition=action.get("smart_condition"),
                )
                session.add(row)

            elif action_type == "trigger_workflow":
                from app.services.runtime_service import trigger_workflow
                await trigger_workflow(
                    session,
                    template_id=action.get("template", ""),
                    context=action.get("context", {}),
                    user_id=user_id,
                )

            elif action_type == "generate_meal_plan":
                import json as _json
                from app.db.models import KnowledgeRow
                plan_data = action.get("plan", {})
                today_str = _user_today().isoformat()
                plan_data["date"] = today_str
                row = KnowledgeRow(
                    user_id=user_id,
                    category="meal_plan",
                    content=_json.dumps(plan_data),
                    tags={"date": today_str},
                )
                session.add(row)

            elif action_type == "update_goal":
                # Upsert a goal by title. Used when the user asks Arlo to
                # change their daily protein / calorie / steps / workouts target.
                from app.db.models import GoalRow as GR
                title = (action.get("title") or "").strip()
                target = action.get("target_value")
                if title and target is not None:
                    existing = (await session.execute(
                        select(GR).where(
                            GR.user_id == user_id,
                            GR.title == title,
                        )
                    )).scalars().first()
                    if existing:
                        existing.target_value = float(target)
                        if action.get("unit"):
                            existing.unit = action["unit"]
                        if action.get("category"):
                            existing.category = action["category"]
                        if existing.status != "active":
                            existing.status = "active"
                    else:
                        row = GR(
                            user_id=user_id,
                            title=title,
                            target_value=float(target),
                            unit=action.get("unit", ""),
                            category=action.get("category", "health"),
                            status="active",
                        )
                        session.add(row)

            elif action_type == "create_event":
                from app.db.models import CalendarEventRow
                from datetime import datetime as dt
                row = CalendarEventRow(
                    user_id=user_id,
                    title=action.get("title", ""),
                    start_time=dt.fromisoformat(action["start_time"]) if action.get("start_time") else dt.now(),
                    end_time=dt.fromisoformat(action["end_time"]) if action.get("end_time") else None,
                    location=action.get("location"),
                    description=action.get("description"),
                )
                session.add(row)

        except Exception as e:
            logger.warning("Failed to process action %s: %s", action_type, e)

    await session.commit()

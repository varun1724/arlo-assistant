"""Arlo Runtime integration — trigger workflows from chat."""

from __future__ import annotations

import uuid
import logging

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import TriggeredWorkflowRow

logger = logging.getLogger("arlo.assistant.runtime")


async def trigger_workflow(
    session: AsyncSession,
    template_id: str,
    context: dict,
    *,
    user_id: uuid.UUID,
) -> TriggeredWorkflowRow:
    """Trigger a workflow on Arlo Runtime and track it."""
    row = TriggeredWorkflowRow(
        user_id=user_id,
        template_id=template_id,
        context=context,
        status="pending",
    )
    session.add(row)
    await session.flush()

    # Call Runtime API
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{settings.arlo_runtime_url}/workflows/from-template/{template_id}",
                headers={"Authorization": f"Bearer {settings.arlo_runtime_token}"},
                json={"initial_context": context},
            )
        if resp.status_code in (200, 201):
            data = resp.json()
            row.runtime_workflow_id = data.get("id")
            row.status = "running"
            logger.info("Triggered workflow %s on Runtime: %s", template_id, row.runtime_workflow_id)
        else:
            row.status = "failed"
            row.result_preview = f"Runtime error: {resp.status_code} {resp.text[:200]}"
            logger.warning("Failed to trigger workflow: %s", resp.text[:200])
    except Exception as e:
        row.status = "failed"
        row.result_preview = f"Connection error: {e}"
        logger.warning("Runtime unreachable: %s", e)

    await session.commit()
    await session.refresh(row)
    return row


async def get_workflows(session: AsyncSession, *, user_id: uuid.UUID) -> list[TriggeredWorkflowRow]:
    result = await session.execute(
        select(TriggeredWorkflowRow)
        .where(TriggeredWorkflowRow.user_id == user_id)
        .order_by(TriggeredWorkflowRow.created_at.desc())
        .limit(20)
    )
    return list(result.scalars().all())


async def get_workflow(session: AsyncSession, workflow_id: uuid.UUID) -> TriggeredWorkflowRow | None:
    return await session.get(TriggeredWorkflowRow, workflow_id)


async def sync_workflow_status(session: AsyncSession, row: TriggeredWorkflowRow) -> TriggeredWorkflowRow:
    """Poll Runtime for latest workflow status."""
    if not row.runtime_workflow_id or row.status in ("succeeded", "failed"):
        return row
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{settings.arlo_runtime_url}/workflows/{row.runtime_workflow_id}",
                headers={"Authorization": f"Bearer {settings.arlo_runtime_token}"},
            )
        if resp.status_code == 200:
            data = resp.json()
            row.status = data.get("status", row.status)
            if data.get("context", {}).get("result_preview"):
                row.result_preview = data["context"]["result_preview"]
            await session.commit()
            await session.refresh(row)
    except Exception:
        pass
    return row

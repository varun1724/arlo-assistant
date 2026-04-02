"""Integrations API — Runtime workflows and HealthKit sync."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.engine import get_db
from app.services import runtime_service, healthkit_service

router = APIRouter(prefix="/integrations", tags=["integrations"])


# ─── Runtime Workflows ──────────────────────────────────

@router.get("/runtime/workflows")
async def list_workflows(db: AsyncSession = Depends(get_db), user_id: uuid.UUID = Depends(get_current_user)):
    workflows = await runtime_service.get_workflows(db, user_id=user_id)
    return {
        "workflows": [_wf_response(w) for w in workflows],
        "count": len(workflows),
    }


@router.get("/runtime/workflows/{workflow_id}")
async def get_workflow(workflow_id: uuid.UUID, db: AsyncSession = Depends(get_db), user_id: uuid.UUID = Depends(get_current_user)):
    wf = await runtime_service.get_workflow(db, workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    wf = await runtime_service.sync_workflow_status(db, wf)
    return _wf_response(wf)


def _wf_response(w) -> dict:
    return {
        "id": str(w.id),
        "template_id": w.template_id,
        "runtime_workflow_id": w.runtime_workflow_id,
        "status": w.status,
        "result_preview": w.result_preview,
        "context": w.context,
        "created_at": w.created_at.isoformat(),
    }


# ─── HealthKit Sync ─────────────────────────────────────

class HealthKitSyncRequest(BaseModel):
    date: str = Field(...)
    steps: Optional[int] = None
    active_calories: Optional[float] = None
    resting_heart_rate: Optional[int] = None
    sleep_hours: Optional[float] = None
    workouts: list[dict] = Field(default_factory=list)


@router.post("/healthkit/sync")
async def sync_healthkit(body: HealthKitSyncRequest, db: AsyncSession = Depends(get_db), user_id: uuid.UUID = Depends(get_current_user)):
    result = await healthkit_service.sync_healthkit(db, body.model_dump(), user_id=user_id)
    return result

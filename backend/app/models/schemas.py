from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SignalIn(BaseModel):
    component_id: str = Field(..., max_length=256)
    component_type: str = Field(..., max_length=64, description="RDBMS, API, CACHE, MCP_HOST, QUEUE, NOSQL, ...")
    severity: str = Field(default="medium", max_length=32)
    message: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime | None = None


class IncidentSummary(BaseModel):
    id: str
    component_id: str
    component_type: str
    severity: str
    alert_tier: str
    status: str
    signal_count: int
    first_signal_at: datetime
    updated_at: datetime | None


class RawSignalOut(BaseModel):
    id: str
    work_item_id: str
    component_id: str
    message: str
    payload: dict[str, Any]
    received_at: datetime


class RcaOut(BaseModel):
    incident_start: datetime
    incident_end: datetime
    root_cause_category: str
    fix_applied: str
    prevention_steps: str
    mttr_seconds: float | None


class WorkItemDetail(BaseModel):
    id: str
    component_id: str
    component_type: str
    severity: str
    alert_tier: str
    status: str
    signal_count: int
    first_signal_at: datetime
    updated_at: datetime | None
    rca: RcaOut | None
    signals: list[RawSignalOut] = Field(default_factory=list)


class RcaUpsert(BaseModel):
    incident_start: datetime
    incident_end: datetime
    root_cause_category: str
    fix_applied: str
    prevention_steps: str


class StatusPatch(BaseModel):
    status: str

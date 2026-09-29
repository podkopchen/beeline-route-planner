"""Strict models for synthetic engineers, event catalogues and capacity reports."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from app.models.enriched_dataset import RequiredSkill, TransportRequirement
from app.models.normalized_dataset import NormalizedOffice, StrictModel, Territory

EngineerLevel = Literal["junior", "middle", "senior"]
EventType = Literal["urgent_request", "request_cancellation", "engineer_unavailable"]


class Engineer(StrictModel):
    engineer_id: str
    territory: Territory
    office_id: str
    shift_start: datetime
    shift_end: datetime
    skills: tuple[RequiredSkill, ...]
    available_transport: TransportRequirement
    level: EngineerLevel


class UrgentRequestPayload(StrictModel):
    synthetic_event_data: Literal[True]
    synthetic_request_id: str
    synthetic_address: str
    required_skill: RequiredSkill
    transport_requirement: TransportRequirement
    service_duration_min: int
    priority: Literal["urgent"]
    window_start: datetime
    window_end: datetime


class RequestCancellationPayload(StrictModel):
    target_request_id: str


class EngineerUnavailablePayload(StrictModel):
    target_engineer_id: str
    unavailable_from: datetime
    unavailable_until: datetime


EventPayload = (
    UrgentRequestPayload | RequestCancellationPayload | EngineerUnavailablePayload
)


class PlanningEvent(StrictModel):
    event_id: str
    event_type: EventType
    occurred_at: datetime
    territory: Territory
    payload: EventPayload
    effect: str
    changes_plan: bool


class TerritoryCapacity(StrictModel):
    territory: Territory
    engineer_count: int
    available_minutes: int
    demand_minutes: int
    reserve_minutes: int
    reserve_ratio: float
    car_engineer_count: int


class WorkforceDataset(StrictModel):
    workforce_seed: int
    engineers: tuple[Engineer, ...]
    offices: tuple[NormalizedOffice, ...]
    events: tuple[PlanningEvent, ...]

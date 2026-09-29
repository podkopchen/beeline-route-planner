"""Typed, immutable domain contract for one-event offline replanning."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from app.models.normalized_dataset import StrictModel, Territory
from app.models.optimizer import OptimizedPlan, OptimizedStop
from app.models.workforce import PlanningEvent


class ReplanRequest(StrictModel):
    event_id: str
    traffic_profile: Literal["standard", "moderate", "peak"] = "standard"


class CommittedStop(StrictModel):
    engineer_id: str
    request_id: str
    sequence: int
    stop: OptimizedStop


class EventApplicationOutcome(StrictModel):
    status: Literal["applied", "cancellation_too_late", "not_fully_applied"]
    message_ru: str
    affected_request_ids: tuple[str, ...] = ()


class RequestChange(StrictModel):
    request_id: str
    before_engineer_id: str | None = None
    after_engineer_id: str | None = None
    before_service_start: datetime | None = None
    after_service_start: datetime | None = None


class PlanDiff(StrictModel):
    event_id: str
    territory: Territory
    effective_time: datetime
    traffic_profile: str
    committed_visit_count: int
    added_urgent_request_ids: tuple[str, ...] = ()
    cancelled_request_ids: tuple[str, ...] = ()
    reassigned: tuple[RequestChange, ...] = ()
    rescheduled: tuple[RequestChange, ...] = ()
    affected_engineer_ids: tuple[str, ...] = ()
    newly_unassigned_request_ids: tuple[str, ...] = ()
    newly_assigned_request_ids: tuple[str, ...] = ()
    emergency_reserve_activated: bool = False
    activated_reserve_engineer_id: str | None = None


class ReplanResult(StrictModel):
    event: PlanningEvent
    base_plan: OptimizedPlan
    replanned_plan: OptimizedPlan
    committed_stops: tuple[CommittedStop, ...]
    outcome: EventApplicationOutcome
    diff: PlanDiff

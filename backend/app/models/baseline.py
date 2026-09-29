"""Typed, deliberately non-optimizing baseline planning result."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from app.models.metrics import PlanMetrics
from app.models.normalized_dataset import StrictModel, Territory

BaselineMode = Literal["all", "east", "southeast", "southcenter"]
UnassignedCode = Literal[
    "no_skill_candidate",
    "no_transport_candidate",
    "no_territory_candidate",
    "shift_unavailable",
    "time_route_infeasible",
]


class BaselineStop(StrictModel):
    request_id: str
    source_order: int
    global_source_order: int
    planned_arrival: datetime
    service_start: datetime
    service_end: datetime
    waiting_minutes: int
    distance_from_previous_km: float
    base_travel_from_previous_minutes: int
    travel_from_previous_minutes: int
    traffic_profile_id: str
    traffic_factor: float
    previous_cache_key: str
    routing_source: str = "fallback"
    geometry: tuple[tuple[float, float], ...] | None = None
    geo_source: str
    geo_precision: str
    geo_approximate: bool
    geo_warning: str | None


class BaselineRoute(StrictModel):
    engineer_id: str
    territory: Territory
    office_id: str
    stops: tuple[BaselineStop, ...]
    total_distance_km: float
    total_travel_minutes: int


class BaselineAssignment(StrictModel):
    request_id: str
    engineer_id: str
    route_stop_index: int


class BaselineUnassigned(StrictModel):
    request_id: str
    code: UnassignedCode
    message: str


class BaselinePlan(StrictModel):
    mode: BaselineMode
    traffic_profile_id: str
    traffic_factor: float
    routes: tuple[BaselineRoute, ...]
    assignments: tuple[BaselineAssignment, ...]
    unassigned: tuple[BaselineUnassigned, ...]
    total_distance_km: float
    assigned_count: int
    unassigned_count: int
    active_engineer_count: int
    metrics: PlanMetrics | None = None

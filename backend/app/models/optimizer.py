"""Typed results and objective bounds for the OR-Tools VRPTW planner."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from app.models.metrics import PlanMetrics
from app.models.normalized_dataset import StrictModel, Territory

OptimizationMode = Literal["all", "east", "southeast", "southcenter"]


class ObjectiveWeights(StrictModel):
    distance_upper_bound_m: int
    active_engineer_penalty: int
    unassigned_request_penalty: int


class OptimizedStop(StrictModel):
    request_id: str
    planned_arrival: datetime
    service_start: datetime
    service_end: datetime
    waiting_minutes: int
    distance_from_previous_km: float
    base_travel_from_previous_minutes: int
    travel_from_previous_minutes: int
    traffic_profile_id: str
    traffic_factor: float
    routing_source: str = "fallback"
    geometry: tuple[tuple[float, float], ...] | None = None
    geo_source: str
    geo_precision: str
    geo_approximate: bool
    geo_warning: str | None


class OptimizedRoute(StrictModel):
    engineer_id: str
    territory: Territory
    office_id: str
    stops: tuple[OptimizedStop, ...]
    total_distance_km: float
    total_travel_minutes: int
    total_work_minutes: int
    total_waiting_minutes: int


class OptimizedUnassigned(StrictModel):
    request_id: str


class OptimizedPlan(StrictModel):
    mode: OptimizationMode
    traffic_profile_id: str
    traffic_factor: float
    routes: tuple[OptimizedRoute, ...]
    unassigned: tuple[OptimizedUnassigned, ...]
    assigned_count: int
    unassigned_count: int
    active_engineer_count: int
    total_distance_km: float
    total_travel_minutes: int
    total_work_minutes: int
    total_waiting_minutes: int
    objective_weights: ObjectiveWeights
    metrics: PlanMetrics | None = None

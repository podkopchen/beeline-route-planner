"""Shared typed metrics for baseline and optimized plans."""

from __future__ import annotations

from datetime import datetime

from app.models.normalized_dataset import StrictModel, Territory


class RouteMetrics(StrictModel):
    engineer_id: str
    territory: Territory
    visit_count: int
    distance_km: float
    travel_minutes: int
    service_minutes: int
    waiting_minutes: int
    route_end: datetime | None
    route_duration_minutes: int


class TerritoryMetrics(StrictModel):
    territory: Territory
    assigned_count: int
    unassigned_count: int
    active_engineer_count: int
    distance_km: float
    travel_minutes: int
    service_minutes: int
    waiting_minutes: int


class PlanMetrics(StrictModel):
    traffic_profile_id: str
    assigned_count: int
    unassigned_count: int
    active_engineer_count: int
    distance_km: float
    travel_minutes: int
    service_minutes: int
    waiting_minutes: int
    routes: tuple[RouteMetrics, ...]
    territories: tuple[TerritoryMetrics, ...]

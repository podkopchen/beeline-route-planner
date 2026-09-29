"""Public API DTOs; domain models are never exposed directly."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

TerritoryId = Literal["all", "east", "southeast", "southcenter"]
PlanKind = Literal["baseline", "optimized"]
TrafficProfileId = Literal["standard", "moderate", "peak"]
AssignmentStatus = Literal["assigned", "unassigned"]


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ErrorDto(ApiModel):
    code: str
    message: str


class RoutingStatusDto(ApiModel):
    mode: Literal["fallback_only", "road_if_available", "road_required"]
    provider_configured: bool
    interactive_geometry_configured: bool
    provider_checked: Literal[False] = False
    road_transport: Literal["car"] = "car"
    non_car_routing: Literal["approximate"] = "approximate"
    input_requests: int
    plan_calculation: Literal["on_demand_then_memory_cache"] = "on_demand_then_memory_cache"
    arbitrary_address_routing_ready: Literal[False] = False


class HealthDto(ApiModel):
    status: Literal["ok"]
    api_version: str
    offline: Literal[True]


class CoordinateDto(ApiModel):
    latitude: float | None
    longitude: float | None
    source: str
    precision: str | None
    approximate: bool | None
    warning: str | None


class PlanContextDto(ApiModel):
    plan_kind: PlanKind
    territory: TerritoryId
    traffic_profile: TrafficProfileId


class SummaryDto(PlanContextDto):
    request_count: int
    assigned_count: int
    unassigned_count: int
    active_engineer_count: int
    total_distance_km: float
    total_travel_minutes: int
    total_service_minutes: int
    total_waiting_minutes: int
    total_route_duration_minutes: int
    comparison: dict[str, int | float] | None = None


class AssignmentDto(ApiModel):
    engineer_id: str
    sequence: int
    arrival: datetime
    service_start: datetime
    service_end: datetime


class StopDto(AssignmentDto):
    request_id: str
    waiting_minutes: int
    travel_minutes: int
    distance_km: float
    base_travel_minutes: int
    adjusted_travel_minutes: int
    routing_source: Literal["road", "fallback", "unresolved"]
    geometry: tuple[tuple[float, float], ...] | None = None
    geometry_status: Literal["road", "same_location", "non_car_transport", "fallback_only", "matrix_missing", "geometry_missing", "unresolved"] = "geometry_missing"
    routing_warning: str | None = None


class RoadGeometryLegDto(ApiModel):
    request_id: str
    sequence: int
    geometry: tuple[tuple[float, float], ...] | None
    source: Literal["cache", "on_demand", "same_location"]


class RoadGeometryRouteDto(ApiModel):
    engineer_id: str
    legs: tuple[RoadGeometryLegDto, ...]
    provider_request_count: int
    preserves_plan: Literal[True] = True


class DiagnosticDto(ApiModel):
    code: str
    text_ru: str
    scope: str
    territory_engineer_count: int
    skill_engineer_count: int
    transport_engineer_count: int
    standalone_feasible_engineer_count: int
    checked_route_count: int
    checked_route_positions: int
    traffic_profile_id: str


class RequestDto(ApiModel):
    request_id: str
    territory: str
    source_order: int
    address: str
    coordinates: CoordinateDto
    window_start: datetime
    window_end: datetime
    service_duration_min: int
    required_skills: tuple[str, ...]
    transport_requirement: str
    priority: str
    assignment_status: AssignmentStatus
    assignment: AssignmentDto | None = None
    diagnostic: DiagnosticDto | None = None


class RequestsPageDto(PlanContextDto):
    items: tuple[RequestDto, ...]
    total: int
    limit: int
    offset: int


class RouteDto(ApiModel):
    engineer_id: str
    territory: str
    office_id: str
    visit_count: int
    distance_km: float
    travel_minutes: int
    service_minutes: int
    waiting_minutes: int
    route_end: datetime | None
    route_duration_minutes: int
    stops: tuple[StopDto, ...]


class PlanDto(PlanContextDto):
    summary: SummaryDto
    routes: tuple[RouteDto, ...]
    unassigned_request_ids: tuple[str, ...]
    unassigned_diagnostics: tuple[DiagnosticDto, ...]


class EngineerDto(ApiModel):
    engineer_id: str
    territory: str
    office_id: str
    skills: tuple[str, ...]
    transport: str
    level: str
    shift_start: datetime
    shift_end: datetime


class EventDto(ApiModel):
    event_id: str
    event_type: str
    territory: str
    occurred_at: datetime
    effect: str
    changes_plan: bool
    payload: dict[str, object]


class TerritoryDto(ApiModel):
    territory: str
    request_count: int
    engineer_count: int
    office_id: str
    office_coordinates: CoordinateDto


class ReplanRequestDto(ApiModel):
    event_id: str
    traffic_profile: TrafficProfileId = "standard"

"""Strict, append-only reference baseline required by the technical brief."""

from __future__ import annotations

from collections import Counter
from datetime import timedelta

from app.core.traffic_config import STANDARD_TRAFFIC_PROFILE_ID, traffic_profile
from app.models.baseline import (
    BaselineAssignment,
    BaselineMode,
    BaselinePlan,
    BaselineRoute,
    BaselineStop,
    BaselineUnassigned,
)
from app.models.enriched_dataset import EnrichedDataset, EnrichedRequest
from app.models.geo import GeoCacheEntry, GeoDataset
from app.models.road import RoadCache
from app.models.workforce import Engineer, WorkforceDataset
from app.services.geocache import geocache_key
from app.services.metrics import calculate_plan_metrics
from app.services.travel import travel_metric

TERRITORY_FILE_ORDER = ("east", "southeast", "southcenter")


def build_baseline_plan(
    enriched: EnrichedDataset,
    workforce: WorkforceDataset,
    geodataset: GeoDataset,
    mode: BaselineMode = "all",
    traffic_profile_id: str = STANDARD_TRAFFIC_PROFILE_ID,
    road_cache: RoadCache | None = None,
) -> BaselinePlan:
    """Process requests once in source order; do not reorder or optimise routes."""
    entries = {entry.cache_key: entry for entry in geodataset.entries}
    profile = traffic_profile(traffic_profile_id)
    offices = {
        office.office_id: entries[geocache_key(office.source_address)]
        for office in workforce.offices
    }
    requests = _ordered_requests(enriched.requests, mode)
    engineers = tuple(
        item for item in workforce.engineers if mode == "all" or item.territory == mode
    )
    route_stops = {engineer.engineer_id: [] for engineer in engineers}
    route_last_entry = {
        engineer.engineer_id: offices[engineer.office_id] for engineer in engineers
    }
    assignments: list[BaselineAssignment] = []
    unassigned: list[BaselineUnassigned] = []

    for global_order, request in enumerate(requests):
        destination = entries[geocache_key(request.source_address)]
        selected: tuple[Engineer, BaselineStop] | None = None
        timing_failures: list[str] = []
        for engineer in engineers:  # declared order is the TЗ tie-breaker
            reason, stop = _try_append(
                engineer,
                request,
                global_order,
                route_stops[engineer.engineer_id],
                route_last_entry[engineer.engineer_id],
                destination,
                profile.profile_id,
                road_cache,
            )
            if stop is not None:
                selected = (engineer, stop)
                break
            if reason in {"shift", "time_route"}:
                timing_failures.append(reason)
        if selected is None:
            unassigned.append(_unassigned_for(request, engineers, timing_failures))
            continue
        engineer, stop = selected
        route_stops[engineer.engineer_id].append(stop)
        route_last_entry[engineer.engineer_id] = destination
        assignments.append(
            BaselineAssignment(
                request_id=request.request_id,
                engineer_id=engineer.engineer_id,
                route_stop_index=len(route_stops[engineer.engineer_id]) - 1,
            )
        )

    routes = tuple(
        _route(engineer, route_stops[engineer.engineer_id])
        for engineer in engineers
        if route_stops[engineer.engineer_id]
    )
    raw_plan = BaselinePlan(
        mode=mode,
        traffic_profile_id=profile.profile_id,
        traffic_factor=profile.traffic_factor,
        routes=routes,
        assignments=tuple(assignments),
        unassigned=tuple(unassigned),
        total_distance_km=round(sum(route.total_distance_km for route in routes), 6),
        assigned_count=len(assignments),
        unassigned_count=len(unassigned),
        active_engineer_count=len(routes),
    )
    return raw_plan.model_copy(
        update={"metrics": calculate_plan_metrics(raw_plan, enriched, workforce)}
    )


def _ordered_requests(
    requests: tuple[EnrichedRequest, ...], mode: BaselineMode
) -> tuple[EnrichedRequest, ...]:
    selected = [
        request for request in requests if mode == "all" or request.territory == mode
    ]
    return tuple(
        sorted(
            selected,
            key=lambda item: (
                TERRITORY_FILE_ORDER.index(item.territory),
                item.source_order,
            ),
        )
    )


def _try_append(
    engineer: Engineer,
    request: EnrichedRequest,
    global_source_order: int,
    stops: list[BaselineStop],
    previous: GeoCacheEntry,
    destination: GeoCacheEntry,
    traffic_profile_id: str,
    road_cache: RoadCache | None,
) -> tuple[str, BaselineStop | None]:
    if engineer.territory != request.territory:
        return "territory", None
    if not set(request.required_skills).issubset(engineer.skills):
        return "skill", None
    if request.transport_requirement == "car" and engineer.available_transport != "car":
        return "transport", None
    metric = travel_metric(
        previous,
        destination,
        engineer.available_transport,
        road_cache,
        traffic_profile_id,
    )
    if metric.distance_km is None or metric.travel_minutes is None:
        return "time_route", None
    departure = engineer.shift_start if not stops else stops[-1].service_end
    arrival = departure + timedelta(minutes=metric.travel_minutes)
    service_start = max(arrival, request.window_start, engineer.shift_start)
    service_end = service_start + timedelta(minutes=request.service_duration_min)
    if service_end > engineer.shift_end:
        return "shift", None
    if service_end > request.window_end:
        return "time_route", None
    waiting = int((service_start - arrival).total_seconds() // 60)
    return "", BaselineStop(
        request_id=request.request_id,
        source_order=request.source_order,
        global_source_order=global_source_order,
        planned_arrival=arrival,
        service_start=service_start,
        service_end=service_end,
        waiting_minutes=waiting,
        distance_from_previous_km=metric.distance_km,
        base_travel_from_previous_minutes=metric.base_travel_minutes,
        travel_from_previous_minutes=metric.travel_minutes,
        traffic_profile_id=metric.traffic_profile_id,
        traffic_factor=metric.traffic_factor,
        previous_cache_key=previous.cache_key,
        routing_source=metric.routing_source,
        geometry=metric.geometry,
        geo_source=destination.geo_source or destination.source,
        geo_precision=destination.precision or "unknown",
        geo_approximate=bool(destination.approximate),
        geo_warning=destination.warning,
    )


def _unassigned_for(
    request: EnrichedRequest,
    engineers: tuple[Engineer, ...],
    timing_failures: list[str],
) -> BaselineUnassigned:
    local = [
        engineer for engineer in engineers if engineer.territory == request.territory
    ]
    if not local:
        return BaselineUnassigned(
            request_id=request.request_id,
            code="no_territory_candidate",
            message="No engineer is available in the request territory.",
        )
    skilled = [
        engineer
        for engineer in local
        if set(request.required_skills).issubset(engineer.skills)
    ]
    if not skilled:
        return BaselineUnassigned(
            request_id=request.request_id,
            code="no_skill_candidate",
            message="No engineer in the territory has all required skills.",
        )
    transport = [
        engineer
        for engineer in skilled
        if request.transport_requirement != "car"
        or engineer.available_transport == "car"
    ]
    if not transport:
        return BaselineUnassigned(
            request_id=request.request_id,
            code="no_transport_candidate",
            message="Skill-compatible engineers lack the required transport.",
        )
    if timing_failures and all(reason == "shift" for reason in timing_failures):
        return BaselineUnassigned(
            request_id=request.request_id,
            code="shift_unavailable",
            message="Every eligible engineer would exceed the end of their shift.",
        )
    return BaselineUnassigned(
        request_id=request.request_id,
        code="time_route_infeasible",
        message="Eligible engineers cannot append travel, waiting, and service within the time window.",
    )


def _route(engineer: Engineer, stops: list[BaselineStop]) -> BaselineRoute:
    return BaselineRoute(
        engineer_id=engineer.engineer_id,
        territory=engineer.territory,
        office_id=engineer.office_id,
        stops=tuple(stops),
        total_distance_km=round(
            sum(stop.distance_from_previous_km for stop in stops), 6
        ),
        total_travel_minutes=sum(stop.travel_from_previous_minutes for stop in stops),
    )


def unassigned_reason_counts(plan: BaselinePlan) -> Counter[str]:
    return Counter(item.code for item in plan.unassigned)

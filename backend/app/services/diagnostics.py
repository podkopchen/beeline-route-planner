"""Deterministic, evidence-only diagnostics for final optimized plans."""

from __future__ import annotations

from datetime import timedelta

from app.models.diagnostics import DiagnosticReport, UnassignedDiagnostic
from app.models.enriched_dataset import EnrichedDataset, EnrichedRequest
from app.models.geo import GeoCacheEntry, GeoDataset
from app.models.optimizer import OptimizedPlan
from app.models.road import RoadCache
from app.models.workforce import Engineer, WorkforceDataset
from app.services.geocache import geocache_key
from app.services.travel import travel_metric

_TEXT = {
    "no_territory_engineer": "В территории заявки нет инженера.",
    "skill_uncovered": "В территории нет инженера с требуемым навыком.",
    "transport_uncovered": "Инженеры с требуемым навыком не имеют нужного транспорта.",
    "window_shift_infeasible": "Заявка не помещается в окно и смену даже при отдельном выезде из офиса.",
    "final_plan_insertion_infeasible": "Заявку нельзя вставить в найденный финальный план без изменения уже назначенных визитов.",
}


class DiagnosticInvariantError(RuntimeError):
    """A final optimized plan left an unassigned request feasibly insertable."""


def diagnose_optimized_plan(
    plan: OptimizedPlan,
    enriched: EnrichedDataset,
    workforce: WorkforceDataset,
    geodataset: GeoDataset,
    road_cache: RoadCache | None = None,
) -> DiagnosticReport:
    """Classify every unassigned request against fixed final routes only."""
    requests = {request.request_id: request for request in enriched.requests}
    entries = {entry.cache_key: entry for entry in geodataset.entries}
    offices = {
        office.office_id: entries[geocache_key(office.source_address)]
        for office in workforce.offices
    }
    routes_by_engineer = {route.engineer_id: route for route in plan.routes}
    diagnostics = tuple(
        _diagnose_request(
            requests[item.request_id],
            plan,
            workforce.engineers,
            requests,
            entries,
            offices,
            routes_by_engineer,
            road_cache,
        )
        for item in plan.unassigned
    )
    report = DiagnosticReport(
        traffic_profile_id=plan.traffic_profile_id, diagnostics=diagnostics
    )
    selected_request_ids = tuple(
        request_id
        for request_id, request in requests.items()
        if plan.mode == "all" or request.territory == plan.mode
    )
    _assert_report_invariants(plan, report, selected_request_ids)
    return report


def _diagnose_request(
    request: EnrichedRequest,
    plan: OptimizedPlan,
    engineers: tuple[Engineer, ...],
    requests: dict[str, EnrichedRequest],
    entries: dict[str, GeoCacheEntry],
    offices: dict[str, GeoCacheEntry],
    routes_by_engineer: dict[str, object],
    road_cache: RoadCache | None = None,
) -> UnassignedDiagnostic:
    local = [
        engineer for engineer in engineers if engineer.territory == request.territory
    ]
    skilled = [
        engineer
        for engineer in local
        if set(request.required_skills).issubset(engineer.skills)
    ]
    transport = [
        engineer
        for engineer in skilled
        if request.transport_requirement == "none"
        or engineer.available_transport == "car"
    ]
    standalone = [
        engineer
        for engineer in transport
        if _standalone_feasible(
            engineer, request, entries, offices, plan.traffic_profile_id, road_cache
        )
    ]
    positions = sum(
        _checked_positions(engineer, routes_by_engineer) for engineer in standalone
    )
    if not local:
        code = "no_territory_engineer"
    elif not skilled:
        code = "skill_uncovered"
    elif not transport:
        code = "transport_uncovered"
    elif not standalone:
        code = "window_shift_infeasible"
    elif _can_insert_fixed(
        request,
        standalone,
        requests,
        entries,
        offices,
        routes_by_engineer,
        plan.traffic_profile_id,
        road_cache,
    ):
        raise DiagnosticInvariantError(
            f"Request {request.request_id} is unassigned but can be inserted into "
            "the fixed final plan without changing assigned visits"
        )
    else:
        code = "final_plan_insertion_infeasible"
    return UnassignedDiagnostic(
        request_id=request.request_id,
        code=code,
        text_ru=_TEXT[code],
        scope=(
            "Проверка выполнена только относительно финального найденного плана; глобальная невозможность не утверждается."
            if code == "final_plan_insertion_infeasible"
            else "Проверка hard constraints заявки в её территории."
        ),
        territory_engineer_count=len(local),
        skill_engineer_count=len(skilled),
        transport_engineer_count=len(transport),
        standalone_feasible_engineer_count=len(standalone),
        checked_route_count=len(standalone),
        checked_route_positions=positions,
        traffic_profile_id=plan.traffic_profile_id,
    )


def _assert_report_invariants(
    plan: OptimizedPlan, report: DiagnosticReport, request_ids: tuple[str, ...]
) -> None:
    if plan.assigned_count + plan.unassigned_count != len(request_ids):
        raise DiagnosticInvariantError(
            "assigned + unassigned does not equal request count"
        )
    unassigned_ids = [item.request_id for item in plan.unassigned]
    diagnostic_ids = [item.request_id for item in report.diagnostics]
    if len(report.diagnostics) != len(unassigned_ids):
        raise DiagnosticInvariantError(
            "diagnostic count does not equal unassigned count"
        )
    if len(diagnostic_ids) != len(set(diagnostic_ids)) or set(diagnostic_ids) != set(
        unassigned_ids
    ):
        raise DiagnosticInvariantError(
            "unassigned IDs do not map one-to-one to diagnostics"
        )
    if sum(1 for _ in report.diagnostics) != plan.unassigned_count:
        raise DiagnosticInvariantError(
            "diagnostic code distribution does not equal unassigned count"
        )


def _standalone_feasible(
    engineer: Engineer,
    request: EnrichedRequest,
    entries: dict[str, GeoCacheEntry],
    offices: dict[str, GeoCacheEntry],
    profile_id: str,
    road_cache: RoadCache | None,
) -> bool:
    metric = travel_metric(
        offices[engineer.office_id],
        entries[geocache_key(request.source_address)],
        engineer.available_transport,
        road_cache,
        profile_id,
    )
    if metric.travel_minutes is None:
        return False
    arrival = engineer.shift_start + timedelta(minutes=metric.travel_minutes)
    service_start = max(arrival, request.window_start, engineer.shift_start)
    service_end = service_start + timedelta(minutes=request.service_duration_min)
    return service_end <= request.window_end and service_end <= engineer.shift_end


def _checked_positions(
    engineer: Engineer, routes_by_engineer: dict[str, object]
) -> int:
    route = routes_by_engineer.get(engineer.engineer_id)
    return len(route.stops) + 1 if route is not None else 1


def _can_insert_fixed(
    request,
    engineers,
    requests,
    entries,
    offices,
    routes_by_engineer,
    profile_id,
    road_cache,
) -> bool:
    candidate_entry = entries[geocache_key(request.source_address)]
    for engineer in engineers:
        route = routes_by_engineer.get(engineer.engineer_id)
        stops = route.stops if route is not None else ()
        for position in range(len(stops) + 1):
            previous_entry = (
                offices[engineer.office_id]
                if position == 0
                else entries[
                    geocache_key(
                        requests[stops[position - 1].request_id].source_address
                    )
                ]
            )
            previous_end = (
                engineer.shift_start
                if position == 0
                else stops[position - 1].service_end
            )
            inbound = travel_metric(
                previous_entry,
                candidate_entry,
                engineer.available_transport,
                road_cache,
                profile_id,
            )
            if inbound.travel_minutes is None:
                continue
            arrival = previous_end + timedelta(minutes=inbound.travel_minutes)
            service_start = max(arrival, request.window_start)
            service_end = service_start + timedelta(
                minutes=request.service_duration_min
            )
            if service_end > request.window_end or service_end > engineer.shift_end:
                continue
            if position == len(stops):
                return True
            next_stop = stops[position]
            next_entry = entries[
                geocache_key(requests[next_stop.request_id].source_address)
            ]
            onward = travel_metric(
                candidate_entry,
                next_entry,
                engineer.available_transport,
                road_cache,
                profile_id,
            )
            if (
                onward.travel_minutes is not None
                and service_end + timedelta(minutes=onward.travel_minutes)
                <= next_stop.planned_arrival
            ):
                return True
    return False

"""Deterministic OR-Tools VRPTW optimiser with lexicographically safe costs."""

from __future__ import annotations

from datetime import timedelta

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from app.core.traffic_config import STANDARD_TRAFFIC_PROFILE_ID, traffic_profile
from app.models.enriched_dataset import EnrichedDataset, EnrichedRequest
from app.models.geo import GeoDataset
from app.models.optimizer import (
    ObjectiveWeights,
    OptimizationMode,
    OptimizedPlan,
    OptimizedRoute,
    OptimizedStop,
    OptimizedUnassigned,
)
from app.models.road import RoadCache
from app.models.workforce import Engineer, WorkforceDataset
from app.services.baseline import TERRITORY_FILE_ORDER
from app.services.geocache import geocache_key
from app.services.metrics import calculate_plan_metrics
from app.services.travel import travel_metric


class OptimizerError(ValueError):
    """Raised when an optimiser input or OR-Tools solve is invalid."""


def objective_weights(
    distance_upper_bound_m: int, vehicle_count: int
) -> ObjectiveWeights:
    """Return provably dominating integer weights for coverage → vehicles → distance."""
    if distance_upper_bound_m < 0 or vehicle_count < 1:
        raise OptimizerError(
            "Objective bounds require non-negative distance and vehicles"
        )
    active_engineer_penalty = distance_upper_bound_m + 1
    return ObjectiveWeights(
        distance_upper_bound_m=distance_upper_bound_m,
        active_engineer_penalty=active_engineer_penalty,
        unassigned_request_penalty=vehicle_count * active_engineer_penalty
        + distance_upper_bound_m
        + 1,
    )


def build_optimized_plan(
    enriched: EnrichedDataset,
    workforce: WorkforceDataset,
    geodataset: GeoDataset,
    mode: OptimizationMode = "all",
    traffic_profile_id: str = STANDARD_TRAFFIC_PROFILE_ID,
    road_cache: RoadCache | None = None,
) -> OptimizedPlan:
    """Solve offline territory-local VRPTW without a return-to-office leg."""
    profile = traffic_profile(traffic_profile_id)
    requests = _ordered_requests(enriched.requests, mode)
    engineers = tuple(
        engineer
        for engineer in workforce.engineers
        if mode == "all" or engineer.territory == mode
    )
    if not engineers:
        raise OptimizerError(f"No engineers for mode {mode!r}")
    entries = {entry.cache_key: entry for entry in geodataset.entries}
    office_entries = {
        office.office_id: entries[geocache_key(office.source_address)]
        for office in workforce.offices
    }
    request_entries = [
        entries[geocache_key(request.source_address)] for request in requests
    ]
    node_entries = request_entries + [
        office_entries[engineer.office_id] for engineer in engineers
    ]
    request_count, vehicle_count = len(requests), len(engineers)
    starts = [request_count + vehicle_index for vehicle_index in range(vehicle_count)]
    manager = pywrapcp.RoutingIndexManager(
        len(node_entries), vehicle_count, starts, starts
    )
    routing = pywrapcp.RoutingModel(manager)

    # Do not materialise vehicle × node × node Pydantic metrics: in `all`
    # that was ~1.7m objects and exhausted memory. OR-Tools asks only a small,
    # repeatable subset; cache those values lazily as lightweight references.
    metrics = {}

    def metric_for(vehicle_index: int, from_node: int, to_node: int):
        key = (engineers[vehicle_index].available_transport, from_node, to_node)
        if key not in metrics:
            metrics[key] = travel_metric(
                node_entries[from_node], node_entries[to_node],
                engineers[vehicle_index].available_transport, road_cache, profile.profile_id,
            )
        return metrics[key]

    # Moscow/MO inputs are far below this bound; the fixed upper bound remains
    # mathematically safe for lexicographic integer costs without eager matrix allocation.
    distance_upper_bound_m = (request_count + vehicle_count) * 1_000_000
    weights = objective_weights(distance_upper_bound_m, vehicle_count)

    def distance_callback_for(vehicle_index: int):
        def distance_callback(from_index: int, to_index: int) -> int:
            if routing.IsEnd(to_index):
                return 0
            from_node, to_node = (
                manager.IndexToNode(from_index),
                manager.IndexToNode(to_index),
            )
            if from_node == to_node:
                return 0
            metric = metric_for(vehicle_index, from_node, to_node)
            if metric.distance_km is None:
                return distance_upper_bound_m + 1
            return round(metric.distance_km * 1000)

        return distance_callback

    for vehicle_index in range(vehicle_count):
        callback_index = routing.RegisterTransitCallback(
            distance_callback_for(vehicle_index)
        )
        routing.SetArcCostEvaluatorOfVehicle(callback_index, vehicle_index)
        routing.SetFixedCostOfVehicle(weights.active_engineer_penalty, vehicle_index)

    def time_callback_for(vehicle_index: int):
        def time_callback(from_index: int, to_index: int) -> int:
            if routing.IsEnd(to_index):
                from_node = manager.IndexToNode(from_index)
                return (
                    requests[from_node].service_duration_min
                    if from_node < request_count
                    else 0
                )
            from_node, to_node = (
                manager.IndexToNode(from_index),
                manager.IndexToNode(to_index),
            )
            if from_node == to_node:
                return 0
            metric = metric_for(vehicle_index, from_node, to_node)
            if metric.travel_minutes is None:
                return 10**7
            service_minutes = (
                requests[from_node].service_duration_min
                if from_node < request_count
                else 0
            )
            return metric.travel_minutes + service_minutes

        return time_callback

    time_callbacks = [
        routing.RegisterTransitCallback(time_callback_for(index))
        for index in range(vehicle_count)
    ]
    horizon = (
        max(
            int((engineer.shift_end - engineer.shift_start).total_seconds() // 60)
            for engineer in engineers
        )
        + 24 * 60
    )
    routing.AddDimensionWithVehicleTransits(
        time_callbacks, 24 * 60, horizon, False, "Time"
    )
    time_dimension = routing.GetDimensionOrDie("Time")
    day_origin = min(engineer.shift_start for engineer in engineers)
    for request_index, request in enumerate(requests):
        index = manager.NodeToIndex(request_index)
        time_dimension.CumulVar(index).SetRange(
            _minutes_since(day_origin, request.window_start),
            _minutes_since(
                day_origin,
                request.window_end - timedelta(minutes=request.service_duration_min),
            ),
        )
        allowed = [
            vehicle_index
            for vehicle_index, engineer in enumerate(engineers)
            if _is_eligible(engineer, request)
        ]
        for vehicle_index in range(vehicle_count):
            if vehicle_index not in allowed:
                routing.VehicleVar(index).RemoveValue(vehicle_index)
        routing.AddDisjunction([index], weights.unassigned_request_penalty)
    for vehicle_index, engineer in enumerate(engineers):
        start, end = routing.Start(vehicle_index), routing.End(vehicle_index)
        shift_start, shift_end = (
            _minutes_since(day_origin, engineer.shift_start),
            _minutes_since(day_origin, engineer.shift_end),
        )
        time_dimension.CumulVar(start).SetRange(shift_start, shift_start)
        time_dimension.CumulVar(end).SetRange(shift_start, shift_end)

    search = pywrapcp.DefaultRoutingSearchParameters()
    search.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION
    )
    # First-solution construction is deterministic; a wall-clock local-search
    # cutoff would make repeated runs depend on machine timing.
    search.time_limit.seconds = 10
    search.solution_limit = 1
    assignment = routing.SolveWithParameters(search)
    if assignment is None:
        raise OptimizerError("OR-Tools found no solution")
    raw_plan = _plan_from_assignment(
        assignment,
        routing,
        manager,
        time_dimension,
        requests,
        engineers,
        node_entries,
        profile.profile_id,
        profile.traffic_factor,
        weights,
        day_origin,
        mode,
        road_cache,
    )
    return raw_plan.model_copy(
        update={"metrics": calculate_plan_metrics(raw_plan, enriched, workforce)}
    )


def _ordered_requests(
    requests: tuple[EnrichedRequest, ...], mode: OptimizationMode
) -> tuple[EnrichedRequest, ...]:
    return tuple(
        sorted(
            (
                request
                for request in requests
                if mode == "all" or request.territory == mode
            ),
            key=lambda item: (
                TERRITORY_FILE_ORDER.index(item.territory),
                item.source_order,
            ),
        )
    )


def _is_eligible(engineer: Engineer, request: EnrichedRequest) -> bool:
    return (
        engineer.territory == request.territory
        and set(request.required_skills).issubset(engineer.skills)
        and (
            request.transport_requirement == "none"
            or engineer.available_transport == "car"
        )
    )


def _minutes_since(origin, value) -> int:
    return int((value - origin).total_seconds() // 60)


def _plan_from_assignment(
    assignment,
    routing,
    manager,
    time_dimension,
    requests,
    engineers,
    node_entries,
    profile_id,
    factor,
    weights,
    day_origin,
    mode,
    road_cache: RoadCache | None,
) -> OptimizedPlan:
    assigned_request_ids: set[str] = set()
    routes: list[OptimizedRoute] = []
    for vehicle_index, engineer in enumerate(engineers):
        index = routing.Start(vehicle_index)
        previous_entry = node_entries[manager.IndexToNode(index)]
        previous_service_end = day_origin + timedelta(
            minutes=assignment.Value(time_dimension.CumulVar(index))
        )
        stops: list[OptimizedStop] = []
        while not routing.IsEnd(index):
            next_index = assignment.Value(routing.NextVar(index))
            if routing.IsEnd(next_index):
                break
            request_index = manager.IndexToNode(next_index)
            request, destination = requests[request_index], node_entries[request_index]
            metric = travel_metric(
                previous_entry,
                destination,
                engineer.available_transport,
                road_cache,
                profile_id,
            )
            arrival = previous_service_end + timedelta(minutes=metric.travel_minutes)
            service_start = day_origin + timedelta(
                minutes=assignment.Value(time_dimension.CumulVar(next_index))
            )
            service_end = service_start + timedelta(
                minutes=request.service_duration_min
            )
            stops.append(
                OptimizedStop(
                    request_id=request.request_id,
                    planned_arrival=arrival,
                    service_start=service_start,
                    service_end=service_end,
                    waiting_minutes=int(
                        (service_start - arrival).total_seconds() // 60
                    ),
                    distance_from_previous_km=metric.distance_km,
                    base_travel_from_previous_minutes=metric.base_travel_minutes,
                    travel_from_previous_minutes=metric.travel_minutes,
                    traffic_profile_id=profile_id,
                    traffic_factor=factor,
                    routing_source=metric.routing_source,
                    geometry=metric.geometry,
                    geo_source=destination.geo_source or destination.source,
                    geo_precision=destination.precision or "unknown",
                    geo_approximate=bool(destination.approximate),
                    geo_warning=destination.warning,
                )
            )
            assigned_request_ids.add(request.request_id)
            previous_entry, previous_service_end, index = (
                destination,
                service_end,
                next_index,
            )
        if stops:
            routes.append(
                OptimizedRoute(
                    engineer_id=engineer.engineer_id,
                    territory=engineer.territory,
                    office_id=engineer.office_id,
                    stops=tuple(stops),
                    total_distance_km=round(
                        sum(stop.distance_from_previous_km for stop in stops), 6
                    ),
                    total_travel_minutes=sum(
                        stop.travel_from_previous_minutes for stop in stops
                    ),
                    total_work_minutes=sum(
                        request.service_duration_min
                        for request in requests
                        if request.request_id in {stop.request_id for stop in stops}
                    ),
                    total_waiting_minutes=sum(stop.waiting_minutes for stop in stops),
                )
            )
    unassigned = tuple(
        OptimizedUnassigned(request_id=request.request_id)
        for request in requests
        if request.request_id not in assigned_request_ids
    )
    return OptimizedPlan(
        mode=mode,
        traffic_profile_id=profile_id,
        traffic_factor=factor,
        routes=tuple(routes),
        unassigned=unassigned,
        assigned_count=len(assigned_request_ids),
        unassigned_count=len(unassigned),
        active_engineer_count=len(routes),
        total_distance_km=round(sum(route.total_distance_km for route in routes), 6),
        total_travel_minutes=sum(route.total_travel_minutes for route in routes),
        total_work_minutes=sum(route.total_work_minutes for route in routes),
        total_waiting_minutes=sum(route.total_waiting_minutes for route in routes),
        objective_weights=weights,
    )

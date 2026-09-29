"""One deterministic metric calculation shared by baseline and optimizer."""

from __future__ import annotations

from app.models.baseline import BaselinePlan
from app.models.enriched_dataset import EnrichedDataset
from app.models.metrics import PlanMetrics, RouteMetrics, TerritoryMetrics
from app.models.optimizer import OptimizedPlan
from app.models.workforce import WorkforceDataset

TERRITORY_ORDER = ("east", "southeast", "southcenter")

PlanLike = BaselinePlan | OptimizedPlan


def calculate_plan_metrics(
    plan: PlanLike, enriched: EnrichedDataset, workforce: WorkforceDataset
) -> PlanMetrics:
    """Calculate no-return visit-leg metrics without changing a plan."""
    requests = {request.request_id: request for request in enriched.requests}
    engineers = {engineer.engineer_id: engineer for engineer in workforce.engineers}
    route_metrics: list[RouteMetrics] = []
    assigned_by_territory = {territory: 0 for territory in TERRITORY_ORDER}
    for route in plan.routes:
        stops = route.stops
        service_minutes = sum(
            requests[stop.request_id].service_duration_min for stop in stops
        )
        metric = RouteMetrics(
            engineer_id=route.engineer_id,
            territory=route.territory,
            visit_count=len(stops),
            distance_km=round(sum(stop.distance_from_previous_km for stop in stops), 6),
            travel_minutes=sum(stop.travel_from_previous_minutes for stop in stops),
            service_minutes=service_minutes,
            waiting_minutes=sum(stop.waiting_minutes for stop in stops),
            route_end=stops[-1].service_end if stops else None,
            route_duration_minutes=(
                int(
                    (
                        stops[-1].service_end - engineers[route.engineer_id].shift_start
                    ).total_seconds()
                    // 60
                )
                if stops
                else 0
            ),
        )
        route_metrics.append(metric)
        assigned_by_territory[route.territory] += metric.visit_count
    unassigned_by_territory = {territory: 0 for territory in TERRITORY_ORDER}
    for item in plan.unassigned:
        unassigned_by_territory[requests[item.request_id].territory] += 1
    territory_metrics = tuple(
        TerritoryMetrics(
            territory=territory,
            assigned_count=assigned_by_territory[territory],
            unassigned_count=unassigned_by_territory[territory],
            active_engineer_count=sum(
                route.territory == territory for route in route_metrics
            ),
            distance_km=round(
                sum(
                    route.distance_km
                    for route in route_metrics
                    if route.territory == territory
                ),
                6,
            ),
            travel_minutes=sum(
                route.travel_minutes
                for route in route_metrics
                if route.territory == territory
            ),
            service_minutes=sum(
                route.service_minutes
                for route in route_metrics
                if route.territory == territory
            ),
            waiting_minutes=sum(
                route.waiting_minutes
                for route in route_metrics
                if route.territory == territory
            ),
        )
        for territory in TERRITORY_ORDER
        if plan.mode == "all" or territory == plan.mode
    )
    return PlanMetrics(
        traffic_profile_id=plan.traffic_profile_id,
        assigned_count=sum(route.visit_count for route in route_metrics),
        unassigned_count=len(plan.unassigned),
        active_engineer_count=len(route_metrics),
        distance_km=round(sum(route.distance_km for route in route_metrics), 6),
        travel_minutes=sum(route.travel_minutes for route in route_metrics),
        service_minutes=sum(route.service_minutes for route in route_metrics),
        waiting_minutes=sum(route.waiting_minutes for route in route_metrics),
        routes=tuple(route_metrics),
        territories=territory_metrics,
    )

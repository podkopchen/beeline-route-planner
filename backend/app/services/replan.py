"""Deterministic one-event replanning with an immutable committed prefix."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.core.enrichment_config import ENRICHMENT_CONFIG
from app.core.traffic_config import traffic_profile
from app.models.enriched_dataset import EnrichedDataset, EnrichedRequest
from app.models.geo import GeoDataset
from app.models.optimizer import (
    OptimizedPlan,
    OptimizedRoute,
    OptimizedStop,
    OptimizedUnassigned,
)
from app.models.replan import (
    CommittedStop,
    EventApplicationOutcome,
    PlanDiff,
    ReplanResult,
)
from app.models.road import RoadCache
from app.models.workforce import (
    Engineer,
    EngineerUnavailablePayload,
    PlanningEvent,
    RequestCancellationPayload,
    UrgentRequestPayload,
    WorkforceDataset,
)
from app.services.geocache import geocache_key
from app.services.metrics import calculate_plan_metrics
from app.services.optimizer import build_optimized_plan
from app.services.travel import travel_metric


class ReplanInvariantError(RuntimeError):
    """A safe failure: no partial replanned plan may be published."""


def build_replanned_plan(
    enriched: EnrichedDataset,
    workforce: WorkforceDataset,
    geo: GeoDataset,
    event: PlanningEvent,
    traffic_profile_id: str,
    road_cache: RoadCache | None = None,
) -> ReplanResult:
    """Apply exactly one catalogue event without mutating inputs or the base snapshot."""
    profile = traffic_profile(traffic_profile_id)
    base = build_optimized_plan(
        enriched, workforce, geo, event.territory, profile.profile_id, road_cache
    )
    committed, prefix_sizes = _committed_prefix(base, workforce, event.occurred_at)
    request_map = {item.request_id: item for item in enriched.requests}
    routes = {route.engineer_id: list(route.stops) for route in base.routes}
    cancelled: list[str] = []
    newly_unassigned: list[str] = []
    newly_assigned: list[str] = []
    affected: set[str] = set()
    outcome = EventApplicationOutcome(
        status="applied", message_ru="Событие применено к изменяемой части плана."
    )
    augmented = enriched

    if isinstance(event.payload, UrgentRequestPayload):
        urgent = _urgent_request(enriched, event)
        augmented = enriched.model_copy(
            update={"requests": enriched.requests + (urgent,)}
        )
        request_map[urgent.request_id] = urgent
        reserve = _emergency_reserve(event, workforce)
        reserve_stops = _rebuild_route(
            reserve, [urgent], 0, [], geo, profile.profile_id, road_cache
        )
        if reserve_stops is not None:
            routes[reserve.engineer_id] = reserve_stops
            workforce = workforce.model_copy(
                update={"engineers": workforce.engineers + (reserve,)}
            )
            affected.add(reserve.engineer_id)
            choice = (reserve.engineer_id, reserve_stops)
        else:
            choice = _insert_urgent(
                routes,
                prefix_sizes,
                urgent,
                request_map,
                workforce,
                geo,
                profile.profile_id,
                road_cache,
            )
        if choice is None:
            newly_unassigned.append(urgent.request_id)
            outcome = EventApplicationOutcome(
                status="not_fully_applied",
                message_ru="Срочную заявку нельзя добавить без нарушения зафиксированных визитов.",
                affected_request_ids=(urgent.request_id,),
            )
        else:
            engineer_id, updated = choice
            routes[engineer_id] = updated
            affected.add(engineer_id)
            newly_assigned.append(urgent.request_id)
    elif isinstance(event.payload, RequestCancellationPayload):
        target = event.payload.target_request_id
        found = _remove_mutable(routes, prefix_sizes, target)
        if found is None:
            outcome = EventApplicationOutcome(
                status="cancellation_too_late",
                message_ru="Отмена получена после начала зафиксированной работы; визит сохранён.",
                affected_request_ids=(target,),
            )
        else:
            affected.add(found)
            cancelled.append(target)
    elif isinstance(event.payload, EngineerUnavailablePayload):
        affected.add(event.payload.target_engineer_id)
        removed = _remove_mutable_for_engineer(
            routes, prefix_sizes, event.payload.target_engineer_id
        )
        newly_unassigned.extend(stop.request_id for stop in removed)
    else:  # pragma: no cover - strict union protects this boundary
        raise ReplanInvariantError("Unsupported event payload")

    plan = _assemble_plan(
        base,
        routes,
        request_map,
        workforce,
        geo,
        augmented,
        profile.profile_id,
        newly_unassigned,
        cancelled,
    )
    diff = PlanDiff(
        event_id=event.event_id,
        territory=event.territory,
        effective_time=event.occurred_at,
        traffic_profile=profile.profile_id,
        committed_visit_count=len(committed),
        added_urgent_request_ids=tuple(newly_assigned),
        cancelled_request_ids=tuple(cancelled),
        affected_engineer_ids=tuple(sorted(affected)),
        newly_unassigned_request_ids=tuple(sorted(newly_unassigned)),
        newly_assigned_request_ids=tuple(newly_assigned),
        emergency_reserve_activated=bool(
            isinstance(event.payload, UrgentRequestPayload)
            and choice is not None
            and choice[0].startswith("reserve-")
        ),
        activated_reserve_engineer_id=choice[0]
        if isinstance(event.payload, UrgentRequestPayload)
        and choice is not None
        and choice[0].startswith("reserve-")
        else None,
    )
    return ReplanResult(
        event=event,
        base_plan=base,
        replanned_plan=plan,
        committed_stops=committed,
        outcome=outcome,
        diff=diff,
    )


def _emergency_reserve(event: PlanningEvent, workforce: WorkforceDataset) -> Engineer:
    """Synthetic incident-only resource; deliberately absent from canonical workforce."""
    office = next(
        item for item in workforce.offices if item.territory == event.territory
    )
    return Engineer(
        engineer_id=f"reserve-{event.territory}-emergency-01",
        territory=event.territory,
        office_id=office.office_id,
        shift_start=event.occurred_at,
        shift_end=next(
            item.shift_end
            for item in workforce.engineers
            if item.territory == event.territory
        ),
        skills=("network_repair",),
        available_transport="car",
        level="senior",
    )


def _committed_prefix(
    plan: OptimizedPlan, workforce: WorkforceDataset, at: datetime
) -> tuple[tuple[CommittedStop, ...], dict[str, int]]:
    engineers = {item.engineer_id: item for item in workforce.engineers}
    committed: list[CommittedStop] = []
    sizes: dict[str, int] = {}
    for route in plan.routes:
        previous_end = engineers[route.engineer_id].shift_start
        size = 0
        for sequence, stop in enumerate(route.stops, 1):
            # service, waiting-at-stop, or an already-started leg commits next stop.
            if (
                stop.service_start <= at
                or stop.planned_arrival <= at
                or previous_end <= at <= stop.planned_arrival
            ):
                committed.append(
                    CommittedStop(
                        engineer_id=route.engineer_id,
                        request_id=stop.request_id,
                        sequence=sequence,
                        stop=stop,
                    )
                )
                size += 1
                previous_end = stop.service_end
            else:
                break
        sizes[route.engineer_id] = size
    return tuple(committed), sizes


def _urgent_request(enriched: EnrichedDataset, event: PlanningEvent) -> EnrichedRequest:
    payload = event.payload
    assert isinstance(payload, UrgentRequestPayload)
    template = next(
        item for item in enriched.requests if item.territory == event.territory
    )
    norm = ENRICHMENT_CONFIG.bk_normatives["Глобальная проблема"]
    # The mapping is deliberately re-read here: an event payload is not authority.
    return template.model_copy(
        update={
            "request_id": payload.synthetic_request_id,
            "source_request_id": payload.synthetic_request_id,
            "source_order": 10**6,
            "source_address": payload.synthetic_address,
            "bk_request_type": "Глобальная проблема",
            "hd_request_type": "Авария",
            "window_start": payload.window_start,
            "window_end": payload.window_end,
            "required_skills": (payload.required_skill,),
            "priority": "urgent",
            "transport_requirement": payload.transport_requirement,
            "normative_work_name": norm.work_name,
            "technical_work_min": norm.technical_work_min,
            "documents_min": norm.documents_min,
            "service_duration_min": norm.service_duration_min,
            "normative_travel_min": norm.normative_travel_min,
            "base_normative_min": norm.base_normative_min,
        }
    )


def _remove_mutable(routes, prefix_sizes, request_id):
    for engineer_id, stops in routes.items():
        for index, stop in enumerate(stops):
            if stop.request_id == request_id and index >= prefix_sizes.get(
                engineer_id, 0
            ):
                del stops[index]
                return engineer_id
    return None


def _remove_mutable_for_engineer(routes, prefix_sizes, engineer_id):
    stops = routes.get(engineer_id, [])
    prefix = prefix_sizes.get(engineer_id, 0)
    removed = stops[prefix:]
    routes[engineer_id] = stops[:prefix]
    return removed


def _insert_urgent(
    routes,
    prefix_sizes,
    urgent,
    request_map,
    workforce,
    geo,
    profile_id,
    road_cache=None,
):
    engineers = {item.engineer_id: item for item in workforce.engineers}
    for engineer_id in sorted(routes):
        engineer = engineers[engineer_id]
        if (
            engineer.territory != urgent.territory
            or urgent.required_skills[0] not in engineer.skills
            or engineer.available_transport != "car"
        ):
            continue
        for position in range(
            prefix_sizes.get(engineer_id, 0), len(routes[engineer_id]) + 1
        ):
            existing = [request_map[stop.request_id] for stop in routes[engineer_id]]
            candidate = existing[:position] + [urgent] + existing[position:]
            rebuilt = _rebuild_route(
                engineer,
                candidate,
                prefix_sizes.get(engineer_id, 0),
                routes[engineer_id],
                geo,
                profile_id,
                road_cache,
            )
            if rebuilt is not None:
                return engineer_id, rebuilt
        # A mutable suffix is explicitly allowed to change after an event.  If
        # insertion cannot keep it, retain only the committed prefix and let
        # displaced work surface honestly as unassigned in the resulting plan.
        prefix_items = [
            request_map[stop.request_id]
            for stop in routes[engineer_id][: prefix_sizes.get(engineer_id, 0)]
        ]
        rebuilt = _rebuild_route(
            engineer,
            prefix_items + [urgent],
            prefix_sizes.get(engineer_id, 0),
            routes[engineer_id],
            geo,
            profile_id,
            road_cache,
        )
        if rebuilt is not None:
            return engineer_id, rebuilt
    return None


def _rebuild_route(
    engineer, items, prefix_size, old_stops, geo, profile_id, road_cache=None
):
    entries = {item.cache_key: item for item in geo.entries}
    previous_entry = (
        entries[geocache_key(next(o.source_address for o in []))]
        if False
        else entries[geocache_key(engineer.office_id)]
        if False
        else None
    )
    # Office key is resolved by ID via geo targets; avoids fabricating a coordinate.
    office_key = next(
        target.cache_key
        for target in geo.targets
        if target.target_id == engineer.office_id
    )
    previous_entry = entries[office_key]
    previous_end = engineer.shift_start
    output = []
    old_by_id = {stop.request_id: stop for stop in old_stops[:prefix_size]}
    for index, request in enumerate(items):
        if index < prefix_size:
            stop = old_by_id.get(request.request_id)
            if stop is None:
                return None
            output.append(stop)
            previous_entry = entries[geocache_key(request.source_address)]
            previous_end = stop.service_end
            continue
        dest = entries[geocache_key(request.source_address)]
        metric = travel_metric(
            previous_entry, dest, engineer.available_transport, road_cache, profile_id
        )
        if metric.travel_minutes is None or metric.distance_km is None:
            return None
        arrival = previous_end + timedelta(minutes=metric.travel_minutes)
        start = max(arrival, request.window_start)
        end = start + timedelta(minutes=request.service_duration_min)
        if end > request.window_end or end > engineer.shift_end:
            return None
        output.append(
            OptimizedStop(
                request_id=request.request_id,
                planned_arrival=arrival,
                service_start=start,
                service_end=end,
                waiting_minutes=int((start - arrival).total_seconds() // 60),
                distance_from_previous_km=metric.distance_km,
                base_travel_from_previous_minutes=metric.base_travel_minutes,
                travel_from_previous_minutes=metric.travel_minutes,
                traffic_profile_id=profile_id,
                traffic_factor=metric.traffic_factor,
                routing_source=metric.routing_source,
                geometry=metric.geometry,
                geo_source=dest.geo_source or dest.source,
                geo_precision=dest.precision or "unknown",
                geo_approximate=bool(dest.approximate),
                geo_warning=dest.warning,
            )
        )
        previous_entry = dest
        previous_end = end
    return output


def _assemble_plan(
    base,
    route_stops,
    request_map,
    workforce,
    geo,
    enriched,
    profile_id,
    newly_unassigned,
    cancelled,
):
    engineers = {item.engineer_id: item for item in workforce.engineers}
    routes = []
    assigned = set()
    for engineer_id in sorted(route_stops):
        stops = tuple(route_stops[engineer_id])
        if not stops:
            continue
        engineer = engineers[engineer_id]
        assigned.update(stop.request_id for stop in stops)
        routes.append(
            OptimizedRoute(
                engineer_id=engineer_id,
                territory=engineer.territory,
                office_id=engineer.office_id,
                stops=stops,
                total_distance_km=round(
                    sum(x.distance_from_previous_km for x in stops), 6
                ),
                total_travel_minutes=sum(x.travel_from_previous_minutes for x in stops),
                total_work_minutes=sum(
                    request_map[x.request_id].service_duration_min for x in stops
                ),
                total_waiting_minutes=sum(x.waiting_minutes for x in stops),
            )
        )
    considered = {
        item.request_id for item in enriched.requests
        if base.mode == "all" or item.territory == base.mode
    }
    unassigned = (considered - assigned - set(cancelled)) | set(newly_unassigned)
    plan = OptimizedPlan(
        mode=base.mode,
        traffic_profile_id=profile_id,
        traffic_factor=traffic_profile(profile_id).traffic_factor,
        routes=tuple(routes),
        unassigned=tuple(OptimizedUnassigned(request_id=x) for x in sorted(unassigned)),
        assigned_count=len(assigned),
        unassigned_count=len(unassigned),
        active_engineer_count=len(routes),
        total_distance_km=round(sum(x.total_distance_km for x in routes), 6),
        total_travel_minutes=sum(x.total_travel_minutes for x in routes),
        total_work_minutes=sum(x.total_work_minutes for x in routes),
        total_waiting_minutes=sum(x.total_waiting_minutes for x in routes),
        objective_weights=base.objective_weights,
    )
    return plan.model_copy(
        update={"metrics": calculate_plan_metrics(plan, enriched, workforce)}
    )

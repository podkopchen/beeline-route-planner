"""Versioned read-only RouteFlow API routes and domain-to-DTO mapping."""

from __future__ import annotations

from types import SimpleNamespace

from fastapi import APIRouter, HTTPException, Query, Request

from app.api.schemas import (
    AssignmentDto,
    CoordinateDto,
    DiagnosticDto,
    EngineerDto,
    EventDto,
    PlanDto,
    ReplanRequestDto,
    RequestDto,
    RequestsPageDto,
    RoadGeometryLegDto,
    RoadGeometryRouteDto,
    RouteDto,
    RoutingStatusDto,
    StopDto,
    SummaryDto,
    TerritoryDto,
)
from app.core.routing_config import routing_config
from app.models.workforce import UrgentRequestPayload
from app.repositories.snapshots import RouteFlowSnapshotRepository
from app.services.explanations import explain_request
from app.services.geocache import geocache_key
from app.services.replan import _emergency_reserve, _urgent_request
from app.services.routing import OsrmHttpRoutingProvider, RoutingUnavailableError

router = APIRouter(prefix="/api/v1")


def _repo(request: Request) -> RouteFlowSnapshotRepository:
    return request.app.state.repository


@router.get("/routing/status", response_model=RoutingStatusDto)
def routing_status(request: Request):
    """Report configuration, not reachability; never probe a routing server here."""
    config = routing_config()
    return RoutingStatusDto(
        mode=config.mode,
        provider_configured=bool(config.base_url),
        interactive_geometry_configured=bool(config.interactive_base_url),
        input_requests=len(_repo(request).inputs().enriched.requests),
    )


@router.post(
    "/plans/{plan_kind}/routes/{engineer_id}/road-geometry",
    response_model=RoadGeometryRouteDto,
)
def build_route_geometry(
    plan_kind: str,
    engineer_id: str,
    request: Request,
    territory: str = Query("east", pattern="^(all|east|southeast|southcenter)$"),
    traffic_profile: str = Query("standard", pattern="^(standard|moderate|peak)$"),
    event_id: str | None = None,
):
    """Build only the selected route shape; assignments and plan metrics stay fixed."""
    if plan_kind not in {"baseline", "optimized"}:
        raise HTTPException(404, "План не найден")
    config = routing_config()
    provider = (
        OsrmHttpRoutingProvider(config.interactive_base_url)
        if config.interactive_base_url
        else None
    )
    try:
        result = _repo(request).route_geometry(
            plan_kind,
            territory,
            traffic_profile,
            engineer_id,
            provider,
            event_id,
        )
    except KeyError as error:
        raise HTTPException(404, "Маршрут не найден") from error
    except RoutingUnavailableError:
        raise
    return RoadGeometryRouteDto(
        engineer_id=result.engineer_id,
        legs=tuple(
            RoadGeometryLegDto(
                request_id=leg.request_id,
                sequence=leg.sequence,
                geometry=leg.geometry,
                source=leg.source,
            )
            for leg in result.legs
        ),
        provider_request_count=result.provider_request_count,
    )


@router.get("/requests/{request_id}/explanation")
def request_explanation(
    request_id: str,
    request: Request,
    plan_kind: str = Query("optimized", pattern="^(baseline|optimized)$"),
    traffic_profile: str = Query("standard", pattern="^(standard|moderate|peak)$"),
    event_id: str | None = None,
):
    """Return evidence already present in a canonical plan or one replan result."""
    repository = _repo(request)
    inputs = repository.inputs()
    source_request = next(
        (item for item in inputs.enriched.requests if item.request_id == request_id),
        None,
    )
    if event_id is None:
        if source_request is None:
            raise HTTPException(404, "Заявка не найдена")
        snapshot = repository.plan(plan_kind, source_request.territory, traffic_profile)
        diagnostic = next(
            (
                item
                for item in (
                    snapshot.diagnostics.diagnostics if snapshot.diagnostics else ()
                )
                if item.request_id == request_id
            ),
            None,
        )
        return explain_request(
            source_request, snapshot.plan, inputs.workforce, plan_kind, diagnostic
        ).model_dump(mode="json")
    try:
        result = repository.replan(event_id, traffic_profile)
    except KeyError as error:
        raise HTTPException(404, "Событие не найдено") from error
    event = result.event
    if (
        source_request is None
        and isinstance(event.payload, UrgentRequestPayload)
        and request_id == event.payload.synthetic_request_id
    ):
        source_request = _urgent_request(inputs.enriched, event)
        workforce = inputs.workforce.model_copy(
            update={
                "engineers": inputs.workforce.engineers
                + (_emergency_reserve(event, inputs.workforce),)
            }
        )
    else:
        workforce = inputs.workforce
    if source_request is None:
        raise HTTPException(404, "Заявка не найдена")
    if source_request.territory != event.territory:
        raise HTTPException(422, "Территория заявки не совпадает с территорией события")
    return explain_request(
        source_request, result.replanned_plan, workforce, "optimized", event_id=event_id
    ).model_dump(mode="json")


@router.post("/replan")
def replan(payload: ReplanRequestDto, request: Request):
    """Apply one catalogue event; event time and territory never come from client input."""
    try:
        result = _repo(request).replan(payload.event_id, payload.traffic_profile)
    except KeyError as error:
        raise HTTPException(404, "Событие не найдено") from error
    inputs = _repo(request).inputs()
    snapshot = SimpleNamespace(
        plan=result.replanned_plan, plan_kind="optimized", diagnostics=None
    )
    count = (
        sum(
            item.territory == result.event.territory
            for item in inputs.enriched.requests
        )
        + 1
    )
    projected_plan = PlanDto(
        plan_kind="optimized",
        territory=result.event.territory,
        traffic_profile=payload.traffic_profile,
        summary=_summary(snapshot, count),
        routes=_routes(snapshot, inputs),
        unassigned_request_ids=tuple(
            item.request_id for item in result.replanned_plan.unassigned
        ),
        unassigned_diagnostics=(),
    )
    return {
        "event": result.event.model_dump(mode="json"),
        "replanned_plan": projected_plan.model_dump(mode="json"),
        "diff": result.diff.model_dump(mode="json"),
        "outcome": result.outcome.model_dump(mode="json"),
        "committed_stops": tuple(
            item.model_dump(mode="json") for item in result.committed_stops
        ),
    }


def _coordinate(inputs, address: str) -> CoordinateDto:
    entry = next(
        item
        for item in inputs.geodataset.entries
        if item.cache_key == geocache_key(address)
    )
    return CoordinateDto(
        latitude=entry.coordinates.latitude if entry.coordinates else None,
        longitude=entry.coordinates.longitude if entry.coordinates else None,
        source=entry.geo_source or entry.source,
        precision=entry.precision,
        approximate=entry.approximate,
        warning=entry.warning,
    )


def _diagnostic(item) -> DiagnosticDto:
    return DiagnosticDto(**item.model_dump(exclude={"request_id"}))


def _summary(snapshot, request_count: int, comparison=None) -> SummaryDto:
    plan = snapshot.plan
    metrics = plan.metrics
    return SummaryDto(
        plan_kind=snapshot.plan_kind,
        territory=plan.mode,
        traffic_profile=plan.traffic_profile_id,
        request_count=request_count,
        assigned_count=metrics.assigned_count,
        unassigned_count=metrics.unassigned_count,
        active_engineer_count=metrics.active_engineer_count,
        total_distance_km=metrics.distance_km,
        total_travel_minutes=metrics.travel_minutes,
        total_service_minutes=metrics.service_minutes,
        total_waiting_minutes=metrics.waiting_minutes,
        total_route_duration_minutes=sum(
            item.route_duration_minutes for item in metrics.routes
        ),
        comparison=comparison,
    )


def _comparison(selected, other) -> dict[str, int | float]:
    """Return selected-minus-other real metrics, never fabricated KPI values."""
    metrics, other_metrics = selected.plan.metrics, other.plan.metrics
    return {
        "assigned_delta": metrics.assigned_count - other_metrics.assigned_count,
        "unassigned_delta": metrics.unassigned_count - other_metrics.unassigned_count,
        "active_engineers_delta": metrics.active_engineer_count
        - other_metrics.active_engineer_count,
        "distance_km_delta": round(metrics.distance_km - other_metrics.distance_km, 6),
        "travel_minutes_delta": metrics.travel_minutes - other_metrics.travel_minutes,
        "service_minutes_delta": metrics.service_minutes
        - other_metrics.service_minutes,
        "waiting_minutes_delta": metrics.waiting_minutes
        - other_metrics.waiting_minutes,
    }


def _routes(snapshot, inputs=None) -> tuple[RouteDto, ...]:
    output = []
    # Targets also contain synthetic urgent IDs; source CSV requests alone do not.
    target_keys = {target.target_id: target.cache_key for target in inputs.geodataset.targets} if inputs is not None else {}
    transports = {item.engineer_id: item.available_transport for item in inputs.workforce.engineers} if inputs is not None else {}
    for route in snapshot.plan.routes:
        previous_key = target_keys.get(route.office_id)
        transport = transports.get(route.engineer_id, "car" if route.engineer_id == "reserve-east-emergency-01" else None)
        stops = []
        for index, stop in enumerate(route.stops, start=1):
            destination_key = target_keys.get(stop.request_id)
            origin_key = getattr(stop, "previous_cache_key", None) or previous_key
            # Preserve provider geometry (a tuple); lazy cache geometry is a model.
            geometry = stop.geometry
            if geometry is None and inputs is not None and origin_key and destination_key and stop.routing_source == "road":
                cached = inputs.road_cache.geometry_for(origin_key, destination_key)
                geometry = cached.coordinates if cached else None
            if geometry is not None and hasattr(geometry, "coordinates"):
                geometry = geometry.coordinates
            if geometry:
                status, warning = "road", None
            elif origin_key and origin_key == destination_key:
                status, warning = "same_location", "Следующий визит в той же точке; отдельная дорожная линия не требуется."
            elif stop.routing_source == "unresolved":
                status, warning = "unresolved", "Координаты участка не разрешены."
            elif transport is not None and transport != "car":
                status, warning = "non_car_transport", "Инженер без автомобиля. Пеший/общественный транспорт ещё не моделируется; время и линия приближённые."
            elif stop.routing_source == "road":
                status, warning = "geometry_missing", "Дорожное время рассчитано, но геометрии этого участка нет в кэше."
            elif routing_config().mode == "fallback_only":
                status, warning = "fallback_only", "Для этого запуска включён приближённый режим расчёта."
            else:
                status, warning = "matrix_missing", "Дорожная матрица не содержит участок; используется приближённый расчёт."
            stops.append(StopDto(
                request_id=stop.request_id,
                engineer_id=route.engineer_id,
                sequence=index,
                arrival=stop.planned_arrival,
                service_start=stop.service_start,
                service_end=stop.service_end,
                waiting_minutes=stop.waiting_minutes,
                travel_minutes=stop.travel_from_previous_minutes,
                distance_km=stop.distance_from_previous_km,
                base_travel_minutes=stop.base_travel_from_previous_minutes,
                adjusted_travel_minutes=stop.travel_from_previous_minutes,
                routing_source=stop.routing_source,
                geometry=geometry,
                geometry_status=status,
                routing_warning=warning,
            ))
            previous_key = destination_key
        metric = next(
            item
            for item in snapshot.plan.metrics.routes
            if item.engineer_id == route.engineer_id
        )
        output.append(
            RouteDto(
                engineer_id=route.engineer_id,
                territory=route.territory,
                office_id=route.office_id,
                visit_count=metric.visit_count,
                distance_km=metric.distance_km,
                travel_minutes=metric.travel_minutes,
                service_minutes=metric.service_minutes,
                waiting_minutes=metric.waiting_minutes,
                route_end=metric.route_end,
                route_duration_minutes=metric.route_duration_minutes,
                stops=tuple(stops),
            )
        )
    return tuple(output)


def _request_dto(inputs, snapshot, item) -> RequestDto:
    route_stops = {
        stop.request_id: (route.engineer_id, index, stop)
        for route in snapshot.plan.routes
        for index, stop in enumerate(route.stops, 1)
    }
    diagnostic_map = {
        d.request_id: d
        for d in (snapshot.diagnostics.diagnostics if snapshot.diagnostics else ())
    }
    stop_data = route_stops.get(item.request_id)
    assignment = (
        None
        if stop_data is None
        else AssignmentDto(
            engineer_id=stop_data[0],
            sequence=stop_data[1],
            arrival=stop_data[2].planned_arrival,
            service_start=stop_data[2].service_start,
            service_end=stop_data[2].service_end,
        )
    )
    return RequestDto(
        request_id=item.request_id,
        territory=item.territory,
        source_order=item.source_order,
        address=item.source_address,
        coordinates=_coordinate(inputs, item.source_address),
        window_start=item.window_start,
        window_end=item.window_end,
        service_duration_min=item.service_duration_min,
        required_skills=item.required_skills,
        transport_requirement=item.transport_requirement,
        priority=item.priority,
        assignment_status="assigned" if assignment else "unassigned",
        assignment=assignment,
        diagnostic=_diagnostic(diagnostic_map[item.request_id])
        if item.request_id in diagnostic_map
        else None,
    )


@router.get("/territories", response_model=tuple[TerritoryDto, ...])
def territories(request: Request):
    inputs = _repo(request).inputs()
    return tuple(
        TerritoryDto(
            territory=territory,
            request_count=sum(
                x.territory == territory for x in inputs.enriched.requests
            ),
            engineer_count=sum(
                x.territory == territory for x in inputs.workforce.engineers
            ),
            office_id=office.office_id,
            office_coordinates=_coordinate(inputs, office.source_address),
        )
        for territory in ("east", "southeast", "southcenter")
        for office in inputs.workforce.offices
        if office.territory == territory
    )


@router.get("/summary", response_model=SummaryDto)
def summary(
    request: Request,
    plan_kind: str = Query("optimized", pattern="^(baseline|optimized)$"),
    territory: str = Query("all", pattern="^(all|east|southeast|southcenter)$"),
    traffic_profile: str = Query("standard", pattern="^(standard|moderate|peak)$"),
):
    repo = _repo(request)
    inputs = repo.inputs()
    snapshot = repo.plan(plan_kind, territory, traffic_profile)
    count = (
        sum(x.territory == territory for x in inputs.enriched.requests)
        if territory != "all"
        else len(inputs.enriched.requests)
    )
    other_kind = "baseline" if plan_kind == "optimized" else "optimized"
    return _summary(
        snapshot,
        count,
        _comparison(snapshot, repo.plan(other_kind, territory, traffic_profile)),
    )


@router.get("/requests", response_model=RequestsPageDto)
def requests_list(
    request: Request,
    plan_kind: str = Query("optimized", pattern="^(baseline|optimized)$"),
    territory: str = Query("all", pattern="^(all|east|southeast|southcenter)$"),
    traffic_profile: str = Query("standard", pattern="^(standard|moderate|peak)$"),
    assignment_status: str | None = Query(None, pattern="^(assigned|unassigned)$"),
    limit: int = Query(50, ge=1, le=205),
    offset: int = Query(0, ge=0),
):
    repo = _repo(request)
    inputs = repo.inputs()
    snapshot = repo.plan(plan_kind, territory, traffic_profile)
    selected = [
        x
        for x in inputs.enriched.requests
        if territory == "all" or x.territory == territory
    ]
    dto = [_request_dto(inputs, snapshot, x) for x in selected]
    if assignment_status:
        dto = [x for x in dto if x.assignment_status == assignment_status]
    return RequestsPageDto(
        plan_kind=plan_kind,
        territory=territory,
        traffic_profile=traffic_profile,
        items=tuple(dto[offset : offset + limit]),
        total=len(dto),
        limit=limit,
        offset=offset,
    )


@router.get("/requests/{request_id}", response_model=RequestDto)
def request_detail(
    request_id: str,
    request: Request,
    plan_kind: str = Query("optimized", pattern="^(baseline|optimized)$"),
    territory: str = Query("all", pattern="^(all|east|southeast|southcenter)$"),
    traffic_profile: str = Query("standard", pattern="^(standard|moderate|peak)$"),
):
    inputs = _repo(request).inputs()
    item = next(
        (
            x
            for x in inputs.enriched.requests
            if x.request_id == request_id
            and (territory == "all" or x.territory == territory)
        ),
        None,
    )
    if item is None:
        raise HTTPException(404, "Заявка не найдена")
    return _request_dto(
        inputs, _repo(request).plan(plan_kind, territory, traffic_profile), item
    )


@router.get("/engineers", response_model=tuple[EngineerDto, ...])
def engineers(
    request: Request,
    territory: str = Query("all", pattern="^(all|east|southeast|southcenter)$"),
):
    return tuple(
        EngineerDto(
            engineer_id=x.engineer_id,
            territory=x.territory,
            office_id=x.office_id,
            skills=x.skills,
            transport=x.available_transport,
            level=x.level,
            shift_start=x.shift_start,
            shift_end=x.shift_end,
        )
        for x in _repo(request).inputs().workforce.engineers
        if territory == "all" or x.territory == territory
    )


@router.get("/engineers/{engineer_id}", response_model=EngineerDto)
def engineer_detail(engineer_id: str, request: Request):
    x = next(
        (
            x
            for x in _repo(request).inputs().workforce.engineers
            if x.engineer_id == engineer_id
        ),
        None,
    )
    if x is None:
        raise HTTPException(404, "Инженер не найден")
    return EngineerDto(
        engineer_id=x.engineer_id,
        territory=x.territory,
        office_id=x.office_id,
        skills=x.skills,
        transport=x.available_transport,
        level=x.level,
        shift_start=x.shift_start,
        shift_end=x.shift_end,
    )


@router.get("/plans/{plan_kind}", response_model=PlanDto)
def plan_detail(
    plan_kind: str,
    request: Request,
    territory: str = Query("all", pattern="^(all|east|southeast|southcenter)$"),
    traffic_profile: str = Query("standard", pattern="^(standard|moderate|peak)$"),
):
    if plan_kind not in {"baseline", "optimized"}:
        raise HTTPException(404, "План не найден")
    repo = _repo(request)
    inputs = repo.inputs()
    snapshot = repo.plan(plan_kind, territory, traffic_profile)
    count = (
        sum(x.territory == territory for x in inputs.enriched.requests)
        if territory != "all"
        else len(inputs.enriched.requests)
    )
    return PlanDto(
        plan_kind=plan_kind,
        territory=territory,
        traffic_profile=traffic_profile,
        summary=_summary(snapshot, count),
        routes=_routes(snapshot, inputs),
        unassigned_request_ids=tuple(x.request_id for x in snapshot.plan.unassigned),
        unassigned_diagnostics=tuple(
            _diagnostic(x)
            for x in (snapshot.diagnostics.diagnostics if snapshot.diagnostics else ())
        ),
    )


@router.get("/events", response_model=tuple[EventDto, ...])
def events(request: Request):
    return tuple(
        EventDto(
            event_id=x.event_id,
            event_type=x.event_type,
            territory=x.territory,
            occurred_at=x.occurred_at,
            effect=x.effect,
            changes_plan=x.changes_plan,
            payload=x.payload.model_dump(),
        )
        for x in _repo(request).inputs().workforce.events
    )


@router.get("/events/{event_id}", response_model=EventDto)
def event_detail(event_id: str, request: Request):
    x = next(
        (x for x in _repo(request).inputs().workforce.events if x.event_id == event_id),
        None,
    )
    if x is None:
        raise HTTPException(404, "Событие не найдено")
    return EventDto(
        event_id=x.event_id,
        event_type=x.event_type,
        territory=x.territory,
        occurred_at=x.occurred_at,
        effect=x.effect,
        changes_plan=x.changes_plan,
        payload=x.payload.model_dump(),
    )

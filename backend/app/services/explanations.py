"""Evidence-only explanations for existing plan facts."""

from __future__ import annotations

from app.models.diagnostics import UnassignedDiagnostic
from app.models.explanations import ExplanationFact, RequestExplanation


def explain_request(
    request,
    plan,
    workforce,
    plan_kind: str,
    diagnostic: UnassignedDiagnostic | None = None,
    event_id: str | None = None,
) -> RequestExplanation:
    """Project existing assignment/diagnostic evidence without ranking claims."""
    stop_data = next(
        (
            (route, index, stop)
            for route in plan.routes
            for index, stop in enumerate(route.stops, 1)
            if stop.request_id == request.request_id
        ),
        None,
    )
    if stop_data is None:
        if diagnostic is None:
            return RequestExplanation(
                request_id=request.request_id,
                status="unassigned",
                title="Заявка не назначена",
                summary="Для заявки нет назначения в выбранном плане.",
                facts=(),
                plan_kind=plan_kind,
                territory=request.territory,
                traffic_profile=plan.traffic_profile_id,
                event_id=event_id,
                evidence_scope="Нет diagnostic evidence для этого контекста.",
            )
        return _unassigned(request, plan_kind, diagnostic, event_id)
    route, sequence, stop = stop_data
    engineer = next(
        item for item in workforce.engineers if item.engineer_id == route.engineer_id
    )
    facts = (
        _fact("engineer_id", "Инженер", engineer.engineer_id),
        _fact("territory", "Территория", request.territory),
        _fact("skills", "Требуемый навык / навыки", ", ".join(request.required_skills)),
        _fact("engineer_skills", "Навыки инженера", ", ".join(engineer.skills)),
        _fact(
            "transport",
            "Требование / транспорт",
            f"{request.transport_requirement} / {engineer.available_transport}",
        ),
        _fact(
            "window",
            "Окно",
            f"{_time(request.window_start)}–{_time(request.window_end)}",
        ),
        _fact(
            "schedule",
            "Прибытие / работа",
            f"{_time(stop.planned_arrival)} / {_time(stop.service_start)}–{_time(stop.service_end)}",
        ),
        _fact(
            "leg",
            "Дорога / ожидание / работа",
            f"{stop.travel_from_previous_minutes} мин / {stop.waiting_minutes} мин / {request.service_duration_min} мин",
        ),
        _fact(
            "route_impact",
            "Место в маршруте",
            f"{sequence} из {len(route.stops)}; {route.total_distance_km:.3f} км",
        ),
    )
    return RequestExplanation(
        request_id=request.request_id,
        status="assigned",
        title="Заявка назначена",
        summary="Заявка включена в найденный план: инженер соответствует обязательным ограничениям, а визит помещается в маршрут и временное окно.",
        facts=facts,
        plan_kind=plan_kind,
        territory=request.territory,
        traffic_profile=plan.traffic_profile_id,
        event_id=event_id,
    )


def _unassigned(request, plan_kind, diagnostic, event_id):
    facts = (
        _fact("diagnostic_code", "Проверенная причина", diagnostic.code),
        _fact(
            "candidates",
            "Инженеры: территория / навык / транспорт",
            f"{diagnostic.territory_engineer_count} / {diagnostic.skill_engineer_count} / {diagnostic.transport_engineer_count}",
        ),
        _fact(
            "feasible",
            "Отдельно выполнимо",
            str(diagnostic.standalone_feasible_engineer_count),
        ),
        _fact(
            "checked",
            "Проверено маршрутов / позиций",
            f"{diagnostic.checked_route_count} / {diagnostic.checked_route_positions}",
        ),
    )
    return RequestExplanation(
        request_id=request.request_id,
        status="unassigned",
        title="Заявка не назначена",
        summary=diagnostic.text_ru,
        facts=facts,
        plan_kind=plan_kind,
        territory=request.territory,
        traffic_profile=diagnostic.traffic_profile_id,
        event_id=event_id,
        evidence_scope=diagnostic.scope,
    )


def _fact(key: str, label: str, value: str) -> ExplanationFact:
    return ExplanationFact(key=key, label_ru=label, value=value)


def _time(value) -> str:
    return value.strftime("%H:%M")

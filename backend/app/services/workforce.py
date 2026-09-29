"""DATA-004 deterministic workforce, event catalogue and sanity checks."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime
from typing import Final

from app.core.enrichment_config import ENRICHMENT_CONFIG
from app.core.workforce_config import (
    ENGINEER_TEMPLATES,
    ENGINEERS_PER_TERRITORY,
    SHIFT_END_HOUR,
    SHIFT_START_HOUR,
    WORKFORCE_SEED,
)
from app.models.enriched_dataset import EnrichedDataset, EnrichedRequest
from app.models.normalized_dataset import Territory
from app.models.workforce import (
    Engineer,
    EngineerUnavailablePayload,
    PlanningEvent,
    RequestCancellationPayload,
    TerritoryCapacity,
    UrgentRequestPayload,
    WorkforceDataset,
)
from app.services.normalization import MOSCOW_TIMEZONE

MAIN_REPLAN_EVENT_ID: Final = "event-east-urgent-1430"
# Synthetic urgent events represent the same emergency category as the
# authoritative BK "Глобальная проблема" normative. No event default exists.
URGENT_NORMATIVE_BK_TYPE: Final = "Глобальная проблема"


class WorkforceContractError(ValueError):
    """Raised when an input dataset cannot satisfy DATA-004 coverage rules."""


def build_workforce_dataset(enriched_dataset: EnrichedDataset) -> WorkforceDataset:
    """Build anonymous engineers and a typed event catalogue without replanning."""

    offices_by_territory = {
        office.territory: office for office in enriched_dataset.offices
    }
    if set(offices_by_territory) != set(ENGINEERS_PER_TERRITORY):
        raise WorkforceContractError(
            "Exactly one source office is required per territory"
        )

    engineers = tuple(
        engineer
        for territory, count in ENGINEERS_PER_TERRITORY.items()
        for engineer in _build_territory_engineers(
            territory,
            offices_by_territory[territory].office_id,
            count,
            enriched_dataset,
        )
    )
    events = _build_events(enriched_dataset, engineers)
    workforce = WorkforceDataset(
        workforce_seed=WORKFORCE_SEED,
        engineers=engineers,
        offices=enriched_dataset.offices,
        events=events,
    )
    assert_workforce_sanity(workforce, enriched_dataset)
    return workforce


def canonical_workforce_json_bytes(workforce: WorkforceDataset) -> bytes:
    """Return a stable serialized representation for reproducibility checks."""

    return json.dumps(
        workforce.model_dump(mode="json"),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def workforce_sha256(workforce: WorkforceDataset) -> str:
    return hashlib.sha256(canonical_workforce_json_bytes(workforce)).hexdigest()


def territory_capacity_report(
    workforce: WorkforceDataset, enriched_dataset: EnrichedDataset
) -> tuple[TerritoryCapacity, ...]:
    """Calculate service-only capacity; travel is intentionally outside DATA-004."""

    reports: list[TerritoryCapacity] = []
    for territory in ENGINEERS_PER_TERRITORY:
        engineers = [
            item for item in workforce.engineers if item.territory == territory
        ]
        requests = [
            item for item in enriched_dataset.requests if item.territory == territory
        ]
        available_minutes = sum(
            int((engineer.shift_end - engineer.shift_start).total_seconds() // 60)
            for engineer in engineers
        )
        demand_minutes = sum(request.service_duration_min for request in requests)
        reserve_minutes = available_minutes - demand_minutes
        reports.append(
            TerritoryCapacity(
                territory=territory,
                engineer_count=len(engineers),
                available_minutes=available_minutes,
                demand_minutes=demand_minutes,
                reserve_minutes=reserve_minutes,
                reserve_ratio=reserve_minutes / available_minutes,
                car_engineer_count=sum(
                    engineer.available_transport == "car" for engineer in engineers
                ),
            )
        )
    return tuple(reports)


def assert_workforce_sanity(
    workforce: WorkforceDataset, enriched_dataset: EnrichedDataset
) -> None:
    """Enforce coverage, shift compatibility and positive service-only reserve."""

    if Counter(engineer.territory for engineer in workforce.engineers) != Counter(
        ENGINEERS_PER_TERRITORY
    ):
        raise WorkforceContractError("Engineer counts do not match territory contract")
    for request in enriched_dataset.requests:
        candidates = _eligible_engineer_count(request, workforce.engineers)
        if candidates < 2:
            raise WorkforceContractError(
                f"Request {request.request_id} has fewer than two local candidates"
            )
        if not any(
            engineer.territory == request.territory
            and _windows_overlap(
                engineer.shift_start,
                engineer.shift_end,
                request.window_start,
                request.window_end,
            )
            for engineer in workforce.engineers
        ):
            raise WorkforceContractError(
                f"Request {request.request_id} has no overlapping local shift"
            )
    for report in territory_capacity_report(workforce, enriched_dataset):
        if report.reserve_minutes <= 0:
            raise WorkforceContractError(
                f"Service capacity is insufficient in {report.territory}"
            )


def _build_territory_engineers(
    territory: Territory,
    office_id: str,
    count: int,
    enriched_dataset: EnrichedDataset,
) -> tuple[Engineer, ...]:
    day = min(
        request.window_start.date()
        for request in enriched_dataset.requests
        if request.territory == territory
    )
    shift_start = datetime(
        day.year, day.month, day.day, SHIFT_START_HOUR, tzinfo=MOSCOW_TIMEZONE
    )
    shift_end = datetime(
        day.year, day.month, day.day, SHIFT_END_HOUR, tzinfo=MOSCOW_TIMEZONE
    )
    return tuple(
        Engineer(
            engineer_id=f"eng-{territory}-{index:02d}",
            territory=territory,
            office_id=office_id,
            shift_start=shift_start,
            shift_end=shift_end,
            skills=template.skills,
            available_transport=template.available_transport,
            level=template.level,
        )
        for index, template in enumerate(ENGINEER_TEMPLATES[:count], start=1)
    )


def _build_events(
    enriched_dataset: EnrichedDataset,
    engineers: tuple[Engineer, ...],
) -> tuple[PlanningEvent, ...]:
    events: list[PlanningEvent] = []
    urgent_minutes = {"east": 30, "southeast": 40, "southcenter": 50}
    for territory in ENGINEERS_PER_TERRITORY:
        day = min(
            request.window_start.date()
            for request in enriched_dataset.requests
            if request.territory == territory
        )
        request = next(
            item for item in enriched_dataset.requests if item.territory == territory
        )
        network_car_engineer = next(
            item
            for item in engineers
            if item.territory == territory
            and "network_repair" in item.skills
            and item.available_transport == "car"
        )
        urgent_at = _event_time(day, 14, urgent_minutes[territory])
        events.extend(
            (
                PlanningEvent(
                    event_id=(
                        MAIN_REPLAN_EVENT_ID
                        if territory == "east"
                        else f"event-{territory}-urgent-{14}{urgent_minutes[territory]:02d}"
                    ),
                    event_type="urgent_request",
                    occurred_at=urgent_at,
                    territory=territory,
                    payload=UrgentRequestPayload(
                        synthetic_event_data=True,
                        synthetic_request_id=f"event-urgent-{territory}-001",
                        synthetic_address=f"Synthetic urgent event location {territory}",
                        required_skill="network_repair",
                        transport_requirement="car",
                        service_duration_min=_urgent_service_duration_from_normative(),
                        priority="urgent",
                        window_start=_event_time(day, 15, 0),
                        window_end=_event_time(day, 17, 0),
                    ),
                    effect="Adds a synthetic urgent visit; a future replan must assign it.",
                    changes_plan=True,
                ),
                PlanningEvent(
                    event_id=f"event-{territory}-cancel-1300",
                    event_type="request_cancellation",
                    occurred_at=_event_time(day, 13, 0),
                    territory=territory,
                    payload=RequestCancellationPayload(
                        target_request_id=request.request_id
                    ),
                    effect="Removes the referenced source request from a future plan.",
                    changes_plan=True,
                ),
                PlanningEvent(
                    event_id=f"event-{territory}-unavailable-1600",
                    event_type="engineer_unavailable",
                    occurred_at=_event_time(day, 16, 0),
                    territory=territory,
                    payload=EngineerUnavailablePayload(
                        target_engineer_id=network_car_engineer.engineer_id,
                        unavailable_from=_event_time(day, 16, 0),
                        unavailable_until=_event_time(day, 20, 0),
                    ),
                    effect="Blocks the referenced engineer for the future replan interval.",
                    changes_plan=True,
                ),
            )
        )
    return tuple(events)


def _urgent_service_duration_from_normative() -> int:
    """Return on-site work duration from NORM-001, never an event override."""

    try:
        return ENRICHMENT_CONFIG.bk_normatives[
            URGENT_NORMATIVE_BK_TYPE
        ].service_duration_min
    except KeyError as error:
        raise WorkforceContractError(
            "Synthetic urgent event has no authoritative emergency normative"
        ) from error


def _eligible_engineer_count(
    request: EnrichedRequest,
    engineers: tuple[Engineer, ...],
) -> int:
    return sum(
        engineer.territory == request.territory
        and set(request.required_skills).issubset(engineer.skills)
        and (
            request.transport_requirement == "none"
            or engineer.available_transport == request.transport_requirement
        )
        for engineer in engineers
    )


def _windows_overlap(
    first_start: datetime,
    first_end: datetime,
    second_start: datetime,
    second_end: datetime,
) -> bool:
    return max(first_start, second_start) < min(first_end, second_end)


def _event_time(day, hour: int, minute: int) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=MOSCOW_TIMEZONE)

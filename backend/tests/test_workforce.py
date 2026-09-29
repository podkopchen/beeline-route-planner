from collections import Counter
from hashlib import sha256
from pathlib import Path

import pytest

from app.core.enrichment_config import ENRICHMENT_CONFIG
from app.services.csv_loader import load_all_synthetic_sources, permitted_source_paths
from app.services.enrichment import enrich_normalized_dataset
from app.services.normalization import normalize_loaded_source_data
from app.services.workforce import (
    MAIN_REPLAN_EVENT_ID,
    URGENT_NORMATIVE_BK_TYPE,
    build_workforce_dataset,
    canonical_workforce_json_bytes,
    territory_capacity_report,
    workforce_sha256,
)

WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
SYNTHETIC_DATASET_DIR = WORKSPACE_ROOT / "Датасет" / "Обезличивание"
SOURCE_HASHES = {
    "Восток Синтетические данные.csv": "35b2e2e34ed488579ed722b55345b73989f277b9b710b66b12d01c5ec38a00b9",
    "Юго-восток Синтетические данные.csv": "c767a9e38f6d21568651cc4dbebe6acaf0a25f72303018a096fcf3c81fc8f331",
    "Югоцентр Синтетические данные.csv": "e553b5b1ad985f2ec62ffe291544a7df1c8622ef5cd80165287d95f45a53a035",
}


@pytest.fixture(scope="module")
def enriched_dataset():
    loaded = load_all_synthetic_sources(SYNTHETIC_DATASET_DIR)
    return enrich_normalized_dataset(normalize_loaded_source_data(loaded))


@pytest.fixture(scope="module")
def workforce(enriched_dataset):
    return build_workforce_dataset(enriched_dataset)


def test_engineer_and_office_counts_match_the_contract(workforce) -> None:
    assert Counter(engineer.territory for engineer in workforce.engineers) == {
        "east": 12,
        "southeast": 12,
        "southcenter": 11,
    }
    assert len(workforce.offices) == 3
    assert all(
        engineer.office_id == f"office:{engineer.territory}"
        for engineer in workforce.engineers
    )


def test_every_request_has_two_local_skill_and_transport_candidates(
    workforce, enriched_dataset
) -> None:
    for request in enriched_dataset.requests:
        candidates = [
            engineer
            for engineer in workforce.engineers
            if engineer.territory == request.territory
            and set(request.required_skills).issubset(engineer.skills)
            and (
                request.transport_requirement == "none"
                or engineer.available_transport == request.transport_requirement
            )
        ]
        assert len(candidates) >= 2, request.request_id


def test_capacity_and_shift_compatibility_are_sane(workforce, enriched_dataset) -> None:
    reports = territory_capacity_report(workforce, enriched_dataset)
    assert {report.territory: report.demand_minutes for report in reports} == {
        "east": 3560,
        "southeast": 4490,
        "southcenter": 2830,
    }
    assert all(report.reserve_minutes > 0 for report in reports)
    assert all(report.reserve_ratio > 0.2 for report in reports)
    assert all(report.car_engineer_count >= 2 for report in reports)
    assert all(engineer.shift_start.hour == 10 for engineer in workforce.engineers)
    assert all(engineer.shift_end.hour == 22 for engineer in workforce.engineers)


def test_nine_typed_events_include_the_main_1430_scenario(workforce) -> None:
    assert len(workforce.events) == 9
    assert Counter(event.territory for event in workforce.events) == {
        "east": 3,
        "southeast": 3,
        "southcenter": 3,
    }
    assert Counter(event.event_type for event in workforce.events) == {
        "urgent_request": 3,
        "request_cancellation": 3,
        "engineer_unavailable": 3,
    }
    main_event = next(
        event for event in workforce.events if event.event_id == MAIN_REPLAN_EVENT_ID
    )
    assert main_event.occurred_at.hour == 14
    assert main_event.occurred_at.minute == 30
    assert main_event.changes_plan is True
    assert main_event.payload.synthetic_event_data is True
    assert main_event.payload.service_duration_min == 80


def test_urgent_duration_cannot_bypass_authoritative_normative(workforce) -> None:
    """Every urgent event derives its duration from the emergency BK mapping."""

    expected = ENRICHMENT_CONFIG.bk_normatives[
        URGENT_NORMATIVE_BK_TYPE
    ].service_duration_min
    urgent_payloads = [
        event.payload
        for event in workforce.events
        if event.event_type == "urgent_request"
    ]
    assert expected == 80
    assert all(payload.service_duration_min == expected for payload in urgent_payloads)


def test_workforce_is_stable_and_sources_remain_unchanged(enriched_dataset) -> None:
    first = build_workforce_dataset(enriched_dataset)
    second = build_workforce_dataset(enriched_dataset)

    assert canonical_workforce_json_bytes(first) == canonical_workforce_json_bytes(
        second
    )
    assert workforce_sha256(first) == workforce_sha256(second)
    assert all(
        "Контрольное распределение" not in path.name
        for path in permitted_source_paths(SYNTHETIC_DATASET_DIR)
    )
    for source_path in permitted_source_paths(SYNTHETIC_DATASET_DIR):
        assert (
            sha256(source_path.read_bytes()).hexdigest()
            == SOURCE_HASHES[source_path.name]
        )

from collections import Counter
from pathlib import Path

import pytest

from app.core.enrichment_config import ENRICHMENT_CONFIG, ENRICHMENT_SEED
from app.services.csv_loader import load_all_synthetic_sources, permitted_source_paths
from app.services.enrichment import (
    EnrichmentError,
    canonical_json_bytes,
    enrich_normalized_dataset,
    enriched_dataset_sha256,
)
from app.services.normalization import normalize_loaded_source_data

WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
SYNTHETIC_DATASET_DIR = WORKSPACE_ROOT / "Датасет" / "Обезличивание"
ALLOWED_SKILLS = {"installation", "subscriber_support", "network_repair"}
ALLOWED_COMPLEXITIES = {"low", "medium", "high"}
ALLOWED_DURATIONS = {20, 30, 70, 80}
ALLOWED_TRANSPORT_REQUIREMENTS = {"none", "car"}


@pytest.fixture(scope="module")
def enriched_dataset():
    loaded = load_all_synthetic_sources(SYNTHETIC_DATASET_DIR)
    return enrich_normalized_dataset(normalize_loaded_source_data(loaded))


def test_enrichment_is_byte_stable_for_same_input_and_seed() -> None:
    loaded = load_all_synthetic_sources(SYNTHETIC_DATASET_DIR)
    normalized = normalize_loaded_source_data(loaded)

    first = enrich_normalized_dataset(normalized)
    second = enrich_normalized_dataset(normalized)

    assert ENRICHMENT_CONFIG.seed == ENRICHMENT_SEED == 2026
    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    assert enriched_dataset_sha256(first) == enriched_dataset_sha256(second)


def test_enrichment_preserves_all_requests_and_source_order(enriched_dataset) -> None:
    assert len(enriched_dataset.requests) == 205
    assert [request.source_order for request in enriched_dataset.requests[:66]] == list(
        range(66)
    )
    assert Counter(request.territory for request in enriched_dataset.requests) == {
        "east": 66,
        "southeast": 83,
        "southcenter": 56,
    }


def test_generated_fields_use_only_the_documented_vocabularies(
    enriched_dataset,
) -> None:
    assert {
        skill
        for request in enriched_dataset.requests
        for skill in request.required_skills
    } <= ALLOWED_SKILLS
    assert {
        request.complexity for request in enriched_dataset.requests
    } <= ALLOWED_COMPLEXITIES
    assert {request.service_duration_min for request in enriched_dataset.requests} <= (
        ALLOWED_DURATIONS
    )
    assert {
        request.transport_requirement for request in enriched_dataset.requests
    } <= ALLOWED_TRANSPORT_REQUIREMENTS
    assert {request.priority for request in enriched_dataset.requests} == {"normal"}


def test_excel_normatives_cover_every_bk_type_and_service_workload(
    enriched_dataset,
) -> None:
    assert Counter(
        request.bk_request_type for request in enriched_dataset.requests
    ) == {
        "Подключение": 95,
        "Глобальная проблема": 21,
        "Дозаказ": 12,
        "Локальная заявка": 77,
    }
    assert all(
        request.base_normative_min
        == request.normative_travel_min + request.service_duration_min
        for request in enriched_dataset.requests
    )
    assert all(
        request.service_duration_min
        == request.technical_work_min + request.documents_min
        for request in enriched_dataset.requests
    )
    assert Counter(
        request.service_duration_min for request in enriched_dataset.requests
    ) == {70: 95, 80: 21, 20: 12, 30: 77}
    assert {
        territory: sum(
            request.service_duration_min
            for request in enriched_dataset.requests
            if request.territory == territory
        )
        for territory in ("east", "southeast", "southcenter")
    } == {"east": 3560, "southeast": 4490, "southcenter": 2830}
    assert (
        sum(request.service_duration_min for request in enriched_dataset.requests)
        == 10880
    )
    assert (
        sum(request.normative_travel_min for request in enriched_dataset.requests)
        == 4100
    )
    assert (
        sum(request.base_normative_min for request in enriched_dataset.requests)
        == 14980
    )


def test_unknown_bk_type_is_a_validation_error_not_a_duration_fallback() -> None:
    loaded = load_all_synthetic_sources(SYNTHETIC_DATASET_DIR)
    normalized = normalize_loaded_source_data(loaded)
    unknown = normalized.requests[0].model_copy(
        update={"bk_request_type": "Unknown BK"}
    )
    invalid = normalized.model_copy(
        update={"requests": (unknown,) + normalized.requests[1:]}
    )
    with pytest.raises(EnrichmentError, match="No work normative"):
        enrich_normalized_dataset(invalid)


def test_control_csv_is_not_a_runtime_input() -> None:
    assert len(permitted_source_paths(SYNTHETIC_DATASET_DIR)) == 3
    assert all(
        "Контрольное распределение" not in path.name
        for path in permitted_source_paths(SYNTHETIC_DATASET_DIR)
    )

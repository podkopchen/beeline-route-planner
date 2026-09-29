from dataclasses import replace
from datetime import datetime
from hashlib import sha256
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.models.normalized_dataset import NormalizedOffice
from app.services.csv_loader import load_all_synthetic_sources, permitted_source_paths
from app.services.normalization import (
    MOSCOW_TIMEZONE,
    SOURCE_DATETIME_FORMAT,
    NormalizationError,
    normalize_loaded_source_data,
)

WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
SYNTHETIC_DATASET_DIR = WORKSPACE_ROOT / "Датасет" / "Обезличивание"
SOURCE_HASHES = {
    "Восток Синтетические данные.csv": (
        "35b2e2e34ed488579ed722b55345b73989f277b9b710b66b12d01c5ec38a00b9"
    ),
    "Юго-восток Синтетические данные.csv": (
        "c767a9e38f6d21568651cc4dbebe6acaf0a25f72303018a096fcf3c81fc8f331"
    ),
    "Югоцентр Синтетические данные.csv": (
        "e553b5b1ad985f2ec62ffe291544a7df1c8622ef5cd80165287d95f45a53a035"
    ),
}


@pytest.fixture(scope="module")
def loaded_sources():
    return load_all_synthetic_sources(SYNTHETIC_DATASET_DIR)


@pytest.fixture(scope="module")
def normalized_dataset(loaded_sources):
    return normalize_loaded_source_data(loaded_sources)


def test_normalization_has_the_three_required_request_counts(normalized_dataset) -> None:
    by_territory = {
        territory: sum(request.territory == territory for request in normalized_dataset.requests)
        for territory in ("east", "southeast", "southcenter")
    }

    assert by_territory == {"east": 66, "southeast": 83, "southcenter": 56}
    assert len(normalized_dataset.requests) == 205


def test_stable_ids_and_source_order_match_the_loader(
    loaded_sources, normalized_dataset
) -> None:
    assert [request.request_id for request in normalized_dataset.requests] == [
        f"{request.territory}:{request.source_request_id}"
        for request in loaded_sources.requests
    ]
    assert [request.source_order for request in normalized_dataset.requests] == [
        request.source_order for request in loaded_sources.requests
    ]
    assert [request.source_order for request in normalized_dataset.requests[:66]] == list(
        range(66)
    )


def test_offices_are_typed_entities_and_never_requests(normalized_dataset) -> None:
    assert len(normalized_dataset.offices) == 3
    assert all(isinstance(office, NormalizedOffice) for office in normalized_dataset.offices)
    assert [office.office_id for office in normalized_dataset.offices] == [
        "office:east",
        "office:southeast",
        "office:southcenter",
    ]
    assert {office.office_id for office in normalized_dataset.offices}.isdisjoint(
        request.request_id for request in normalized_dataset.requests
    )


def test_connection_is_nullable_and_the_raw_value_is_retained(normalized_dataset) -> None:
    east_requests = [
        request for request in normalized_dataset.requests if request.territory == "east"
    ]
    other_requests = [
        request for request in normalized_dataset.requests if request.territory != "east"
    ]

    assert sum(request.connection is None for request in east_requests) == 32
    assert {request.connection for request in east_requests if request.connection} == {
        "FMC",
        "FTTB",
    }
    assert all(request.connection is None for request in other_requests)
    assert all("Подключение" not in request.source_fields for request in other_requests)


def test_source_datetimes_are_moscow_aware_and_not_invented(
    loaded_sources, normalized_dataset
) -> None:
    source_request = loaded_sources.requests[0]
    normalized_request = normalized_dataset.requests[0]

    assert normalized_request.window_start == datetime.strptime(
        source_request.fields["Начало"], SOURCE_DATETIME_FORMAT
    ).replace(tzinfo=MOSCOW_TIMEZONE)
    assert normalized_request.window_end == datetime.strptime(
        source_request.fields["Окончание"], SOURCE_DATETIME_FORMAT
    ).replace(tzinfo=MOSCOW_TIMEZONE)
    assert normalized_request.window_start.tzinfo == MOSCOW_TIMEZONE
    assert normalized_request.window_end.tzinfo == MOSCOW_TIMEZONE


def test_empty_window_end_fails_instead_of_being_invented(loaded_sources) -> None:
    request = loaded_sources.requests[0]
    incomplete_request = replace(
        request,
        fields={**request.fields, "Окончание": ""},
    )
    first_territory = loaded_sources.territories[0]
    incomplete_territory = replace(
        first_territory,
        requests=(incomplete_request, *first_territory.requests[1:]),
    )
    incomplete_data = replace(
        loaded_sources,
        territories=(incomplete_territory, *loaded_sources.territories[1:]),
    )

    with pytest.raises(NormalizationError, match="empty required"):
        normalize_loaded_source_data(incomplete_data)


def test_normalized_models_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        NormalizedOffice(
            office_id="office:east",
            territory="east",
            source_filename="source.csv",
            source_line=2,
            source_address="Москва",
            unexpected="value",
        )


def test_normalization_does_not_change_source_csv_hashes() -> None:
    for source_path in permitted_source_paths(SYNTHETIC_DATASET_DIR):
        assert sha256(source_path.read_bytes()).hexdigest() == SOURCE_HASHES[source_path.name]

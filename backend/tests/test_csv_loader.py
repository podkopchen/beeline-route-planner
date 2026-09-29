from pathlib import Path

import pytest

from app.services.csv_loader import (
    CSV_DELIMITER,
    CSV_ENCODING,
    SYNTHETIC_SOURCES,
    CsvContractError,
    is_valid_source_request_id,
    load_all_synthetic_sources,
    permitted_source_paths,
)

WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
SYNTHETIC_DATASET_DIR = WORKSPACE_ROOT / "Датасет" / "Обезличивание"


@pytest.fixture(scope="module")
def loaded_sources():
    return load_all_synthetic_sources(SYNTHETIC_DATASET_DIR)


def test_allowlist_has_exactly_three_synthetic_files() -> None:
    paths = permitted_source_paths(SYNTHETIC_DATASET_DIR)

    assert [source.territory for source in SYNTHETIC_SOURCES] == [
        "east",
        "southeast",
        "southcenter",
    ]
    assert [path.name for path in paths] == [
        "Восток Синтетические данные.csv",
        "Юго-восток Синтетические данные.csv",
        "Югоцентр Синтетические данные.csv",
    ]
    assert all("Контрольное распределение" not in path.name for path in paths)
    assert all(path.is_file() for path in paths)


def test_loader_reads_cp1251_semicolon_sources_and_separates_offices(
    loaded_sources,
) -> None:
    by_territory = {territory.territory: territory for territory in loaded_sources.territories}

    assert CSV_ENCODING == "cp1251"
    assert CSV_DELIMITER == ";"
    assert set(by_territory) == {"east", "southeast", "southcenter"}
    assert len(loaded_sources.offices) == 3
    assert all(office.address.startswith("г") for office in loaded_sources.offices)
    assert all(
        "Адрес офиса" not in request.source_request_id.casefold()
        for request in loaded_sources.requests
    )


def test_valid_request_counts_match_the_source_contract(loaded_sources) -> None:
    request_counts = {
        territory.territory: len(territory.requests)
        for territory in loaded_sources.territories
    }

    assert request_counts == {"east": 66, "southeast": 83, "southcenter": 56}
    assert len(loaded_sources.requests) == 205


def test_request_order_and_optional_connection_column_are_preserved(loaded_sources) -> None:
    by_territory = {territory.territory: territory for territory in loaded_sources.territories}
    east = by_territory["east"]

    assert [request.source_order for request in east.requests] == list(range(66))
    assert all(is_valid_source_request_id(request.source_request_id) for request in east.requests)
    assert "Подключение" in east.headers
    assert "Подключение" not in by_territory["southeast"].headers
    assert "Подключение" not in by_territory["southcenter"].headers


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("74198", True),
        (" 74198 ", True),
        ("", False),
        ("Адрес Офиса", False),
        ("74-198", False),
        ("٧٤١٩٨", False),
    ],
)
def test_only_ascii_digits_are_valid_source_request_ids(
    value: str,
    expected: bool,
) -> None:
    assert is_valid_source_request_id(value) is expected


def test_missing_allowlisted_source_fails_without_csv_discovery() -> None:
    missing_directory = WORKSPACE_ROOT / "missing-synthetic-source-directory"

    with pytest.raises(CsvContractError, match="Synthetic source is missing"):
        load_all_synthetic_sources(missing_directory)

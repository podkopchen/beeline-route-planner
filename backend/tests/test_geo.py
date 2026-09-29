from pathlib import Path
from unittest.mock import patch

from app.models.geo import Coordinates, GeoCacheEntry
from app.services.csv_loader import load_all_synthetic_sources, permitted_source_paths
from app.services.enrichment import enrich_normalized_dataset
from app.services.geocache import (
    UNRESOLVED_WARNING,
    build_offline_geodataset,
    geocache_key,
    normalize_address,
)
from app.services.normalization import normalize_loaded_source_data
from app.services.travel import (
    fallback_travel_matrix,
    fallback_travel_metric,
    haversine_distance_km,
)
from app.services.workforce import build_workforce_dataset

WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
SYNTHETIC_DATASET_DIR = WORKSPACE_ROOT / "Датасет" / "Обезличивание"


def _entry(key: str, latitude: float, longitude: float) -> GeoCacheEntry:
    return GeoCacheEntry(
        cache_key=key,
        normalized_address=key,
        coordinates=Coordinates(latitude=latitude, longitude=longitude),
        source="manual_cache",
        status="resolved",
        warning=None,
    )


def test_geo_cache_keys_are_stable_across_address_formatting() -> None:
    assert normalize_address("  Москва, ул. Тестовая, 1 ") == "москва ул тестовая 1"
    assert geocache_key("Москва, ул. Тестовая, 1") == geocache_key(
        " мОСКВА ул ТЕСТОВАЯ 1 "
    )


def test_haversine_known_coordinates_and_fallback_units() -> None:
    origin = Coordinates(latitude=0.0, longitude=0.0)
    destination = Coordinates(latitude=0.0, longitude=1.0)
    assert 111.1 < haversine_distance_km(origin, destination) < 111.3
    metric = fallback_travel_metric(
        _entry("origin", 0.0, 0.0), _entry("destination", 0.0, 1.0)
    )
    assert metric.distance_km is not None and metric.distance_km > 138
    assert metric.travel_minutes is not None and metric.travel_minutes > 0


def test_matrix_has_zero_diagonal_symmetry_and_explicit_unresolved_warning() -> None:
    first = _entry("first", 55.7558, 37.6173)
    second = _entry("second", 59.9343, 30.3351)
    matrix = fallback_travel_matrix((first, second))
    by_pair = {(item.origin_cache_key, item.destination_cache_key): item for item in matrix}
    assert by_pair[("first", "first")].distance_km == 0.0
    assert by_pair[("first", "first")].travel_minutes == 0
    assert by_pair[("first", "second")].distance_km == by_pair[("second", "first")].distance_km
    assert by_pair[("first", "second")].travel_minutes == by_pair[("second", "first")].travel_minutes
    unresolved = GeoCacheEntry(
        cache_key="missing",
        normalized_address="missing",
        coordinates=None,
        source="unresolved",
        status="unresolved",
        warning=UNRESOLVED_WARNING,
    )
    assert fallback_travel_metric(first, unresolved).warning is not None


def test_offline_geo_build_has_no_network_and_preserves_all_targets() -> None:
    with patch("socket.create_connection", side_effect=AssertionError("network called")):
        loaded = load_all_synthetic_sources(SYNTHETIC_DATASET_DIR)
        enriched = enrich_normalized_dataset(normalize_loaded_source_data(loaded))
        workforce = build_workforce_dataset(enriched)
        geodataset = build_offline_geodataset(enriched, workforce)

    assert len([item for item in geodataset.targets if item.target_kind == "request"]) == 205
    assert len([item for item in geodataset.targets if item.target_kind == "office"]) == 3
    assert len([item for item in geodataset.targets if item.target_kind == "synthetic_event"]) == 3
    assert all(item.status == "unresolved" for item in geodataset.entries)
    assert all(item.warning == UNRESOLVED_WARNING for item in geodataset.entries)
    assert all(
        "Контрольное распределение" not in path.name
        for path in permitted_source_paths(SYNTHETIC_DATASET_DIR)
    )

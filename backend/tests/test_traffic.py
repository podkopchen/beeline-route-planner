import json
import math
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.traffic_config import TrafficProfileError
from app.models.geo import Coordinates, GeoCacheEntry
from app.services.baseline import build_baseline_plan
from app.services.csv_loader import load_all_synthetic_sources
from app.services.enrichment import enrich_normalized_dataset
from app.services.geocache import build_offline_geodataset
from app.services.normalization import normalize_loaded_source_data
from app.services.travel import fallback_travel_metric
from app.services.workforce import build_workforce_dataset

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = PROJECT_ROOT.parent
SOURCE_DIRECTORY = WORKSPACE_ROOT / "Датасет" / "Обезличивание"
CACHE_PATH = PROJECT_ROOT / "data" / "generated" / "geocache.json"


def _entry(key: str, latitude: float, longitude: float) -> GeoCacheEntry:
    return GeoCacheEntry(
        cache_key=key,
        normalized_address=key,
        coordinates=Coordinates(latitude=latitude, longitude=longitude),
        source="manual_cache",
        status="resolved",
        warning=None,
    )


def _inputs():
    enriched = enrich_normalized_dataset(
        normalize_loaded_source_data(load_all_synthetic_sources(SOURCE_DIRECTORY))
    )
    workforce = build_workforce_dataset(enriched)
    entries = tuple(
        GeoCacheEntry.model_validate(item)
        for item in json.loads(CACHE_PATH.read_text(encoding="utf-8"))["entries"]
    )
    return enriched, workforce, build_offline_geodataset(enriched, workforce, entries)


def test_traffic_profiles_apply_formula_once_and_keep_distance_constant() -> None:
    origin, destination = (
        _entry("origin", 55.75, 37.60),
        _entry("destination", 55.90, 37.90),
    )
    standard = fallback_travel_metric(origin, destination)
    moderate = fallback_travel_metric(origin, destination, "moderate")
    peak = fallback_travel_metric(origin, destination, "peak")
    assert standard.travel_minutes == standard.base_travel_minutes
    assert moderate.travel_minutes == math.ceil(
        moderate.base_unrounded_travel_minutes * 1.15
    )
    assert peak.travel_minutes == math.ceil(peak.base_unrounded_travel_minutes * 1.35)
    assert peak.travel_minutes >= moderate.travel_minutes >= standard.travel_minutes
    assert standard.distance_km == moderate.distance_km == peak.distance_km
    assert fallback_travel_metric(origin, origin, "peak").travel_minutes == 0


def test_unknown_profile_is_explicit_and_no_network_is_used() -> None:
    origin, destination = (
        _entry("origin", 55.75, 37.60),
        _entry("destination", 55.90, 37.90),
    )
    with pytest.raises(TrafficProfileError, match="Unknown traffic_profile_id"):
        fallback_travel_metric(origin, destination, "unknown")
    with patch(
        "socket.create_connection", side_effect=AssertionError("network called")
    ):
        assert (
            fallback_travel_metric(origin, destination, "peak").travel_minutes
            is not None
        )


def test_profiles_do_not_change_normatives_and_standard_preserves_baseline() -> None:
    enriched, workforce, geodataset = _inputs()
    assert sum(item.service_duration_min for item in enriched.requests) == 10880
    assert sum(item.normative_travel_min for item in enriched.requests) == 4100
    for mode, expected in {
        "all": (92, 113, 31, 735.449345),
        "east": (27, 39, 11, 159.808414),
        "southeast": (40, 43, 11, 474.561451),
        "southcenter": (25, 31, 9, 101.07948),
    }.items():
        default = build_baseline_plan(enriched, workforce, geodataset, mode)
        standard = build_baseline_plan(
            enriched, workforce, geodataset, mode, "standard"
        )
        assert default == standard
        assert (
            standard.assigned_count,
            standard.unassigned_count,
            standard.active_engineer_count,
            standard.total_distance_km,
        ) == expected
    moderate_one = build_baseline_plan(
        enriched, workforce, geodataset, "all", "moderate"
    )
    moderate_two = build_baseline_plan(
        enriched, workforce, geodataset, "all", "moderate"
    )
    assert moderate_one == moderate_two
    assert moderate_one.traffic_factor == 1.15
    with pytest.raises(TrafficProfileError, match="Unknown traffic_profile_id"):
        build_baseline_plan(enriched, workforce, geodataset, "all", "unknown")

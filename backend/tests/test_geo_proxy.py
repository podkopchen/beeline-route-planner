import json
from pathlib import Path
from unittest.mock import patch

from app.models.geo import GeoCacheEntry
from app.services.csv_loader import load_all_synthetic_sources
from app.services.enrichment import enrich_normalized_dataset
from app.services.geo_proxy import enrich_geodataset_with_proxies
from app.services.geocache import build_offline_geodataset
from app.services.normalization import normalize_loaded_source_data
from app.services.travel import fallback_travel_matrix, fallback_travel_metric
from app.services.workforce import build_workforce_dataset

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = PROJECT_ROOT.parent
SOURCE_DIRECTORY = WORKSPACE_ROOT / "\u0414\u0430\u0442\u0430\u0441\u0435\u0442" / "\u041e\u0431\u0435\u0437\u043b\u0438\u0447\u0438\u0432\u0430\u043d\u0438\u0435"
CACHE_PATH = PROJECT_ROOT / "data" / "generated" / "geocache.json"


def _inputs() -> tuple[object, object, object]:
    enriched = enrich_normalized_dataset(normalize_loaded_source_data(load_all_synthetic_sources(SOURCE_DIRECTORY)))
    workforce = build_workforce_dataset(enriched)
    entries = tuple(
        GeoCacheEntry.model_validate(item)
        for item in json.loads(CACHE_PATH.read_text(encoding="utf-8"))["entries"]
    )
    return enriched, workforce, build_offline_geodataset(enriched, workforce, entries)


def test_proxy_result_is_complete_deterministic_and_network_free() -> None:
    enriched, workforce, geodataset = _inputs()
    synthetic = next(entry for entry in geodataset.entries if entry.geo_source == "synthetic_proxy")
    reset_entries = tuple(
        entry.model_copy(update={"coordinates": None, "status": "unresolved"})
        if entry.cache_key == synthetic.cache_key
        else entry
        for entry in geodataset.entries
    )
    reset_dataset = geodataset.model_copy(update={"entries": reset_entries})
    with patch("socket.create_connection", side_effect=AssertionError("network called")):
        first = enrich_geodataset_with_proxies(reset_dataset, enriched, workforce)
        second = enrich_geodataset_with_proxies(reset_dataset, enriched, workforce)

    assert first == second
    assert all(entry.coordinates is not None for entry in first.entries)
    assert all(entry.status == "resolved" for entry in first.entries)
    restored = next(entry for entry in first.entries if entry.cache_key == synthetic.cache_key)
    assert restored.geo_source == "synthetic_proxy"


def test_proxy_stays_in_locality_cluster_and_urgent_inherits_request_coordinates() -> None:
    enriched, workforce, geodataset = _inputs()
    completed = enrich_geodataset_with_proxies(geodataset, enriched, workforce)
    by_key = {entry.cache_key: entry for entry in completed.entries}
    for entry in completed.entries:
        if entry.geo_source == "synthetic_proxy" and "\u043a\u0430\u0448\u0438\u0440" in entry.normalized_address:
            assert entry.coordinates is not None and entry.coordinates.latitude < 55.3
        if entry.geo_source == "synthetic_proxy" and "\u0441\u0442\u0443\u043f\u0438\u043d" in entry.normalized_address:
            assert entry.coordinates is not None and entry.coordinates.latitude < 55.3
    request_keys = {target.target_id: target.cache_key for target in completed.targets if target.target_kind == "request"}
    for target in completed.targets:
        if target.target_kind != "synthetic_event":
            continue
        entry = by_key[target.cache_key]
        assert entry.location_source_request_id is not None
        assert entry.coordinates == by_key[request_keys[entry.location_source_request_id]].coordinates


def test_haversine_is_defined_for_every_completed_cache_entry() -> None:
    enriched, workforce, geodataset = _inputs()
    completed = enrich_geodataset_with_proxies(geodataset, enriched, workforce)
    metric = fallback_travel_metric(completed.entries[0], completed.entries[-1])
    assert metric.distance_km is not None
    assert metric.travel_minutes is not None
    assert all(item.distance_km is not None for item in fallback_travel_matrix(completed.entries))

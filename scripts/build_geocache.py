"""Explicit GEO cache build; online work is opt-in, observable, and never implicit."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.geo_config import NOMINATIM_THROTTLE_SECONDS, NOMINATIM_URL
from app.models.geo import GeoCacheEntry
from app.services.csv_loader import load_all_synthetic_sources
from app.services.enrichment import enrich_normalized_dataset
from app.services.geocache import (
    build_offline_geodataset,
    geocache_key,
    normalize_address,
)
from app.services.nominatim import (
    OnlineLookupStatistics,
    resolve_address_chain,
    resolve_unresolved_entries,
    unresolved_chain_entry,
)
from app.services.normalization import normalize_loaded_source_data
from app.services.workforce import build_workforce_dataset

WORKSPACE_ROOT = PROJECT_ROOT.parent
SOURCE_DIRECTORY = WORKSPACE_ROOT / "\u0414\u0430\u0442\u0430\u0441\u0435\u0442" / "\u041e\u0431\u0435\u0437\u043b\u0438\u0447\u0438\u0432\u0430\u043d\u0438\u0435"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "generated" / "geocache.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--online", action="store_true", help="Report or explicitly refresh Nominatim entries.")
    parser.add_argument(
        "--refresh-unresolved",
        action="store_true",
        help="Allow --online to query unresolved non-synthetic cache entries.",
    )
    parser.add_argument(
        "--probe", action="store_true", help="Send exactly one Nominatim request for an office."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    if arguments.refresh_unresolved and not arguments.online:
        parser.error("--refresh-unresolved requires --online")
    if arguments.probe and (arguments.online or arguments.refresh_unresolved):
        parser.error("--probe cannot be combined with bulk online options")

    enriched = enrich_normalized_dataset(
        normalize_loaded_source_data(load_all_synthetic_sources(SOURCE_DIRECTORY))
    )
    workforce = build_workforce_dataset(enriched)
    if arguments.probe:
        _print_probe(workforce.offices[0].source_address)
        return

    prior_entries = _load_entries(arguments.output)
    geodataset = build_offline_geodataset(enriched, workforce, prior_entries)
    entries = geodataset.entries
    if arguments.online:
        if arguments.refresh_unresolved:
            entries, statistics = _run_atomic_address_chain(
                entries,
                total_targets=len(geodataset.targets),
                raw_addresses={target.cache_key: target.address for target in geodataset.targets},
                output=arguments.output,
            )
        else:
            entries, statistics = resolve_unresolved_entries(
                entries,
                total_targets=len(geodataset.targets),
                refresh_unresolved=False,
                throttle_seconds=NOMINATIM_THROTTLE_SECONDS,
            )
        print(json.dumps({"online_statistics": statistics.as_dict()}, ensure_ascii=True, sort_keys=True))
    else:
        _write_entries_atomic(arguments.output, entries)


def _print_probe(address: str) -> None:
    entry = GeoCacheEntry(
        cache_key=geocache_key(address),
        normalized_address=normalize_address(address),
        coordinates=None,
        source="unresolved",
        status="unresolved",
        warning="Diagnostic probe only; cache is not changed.",
    )
    resolution = resolve_address_chain(entry, raw_address=address)
    payload = {
        "endpoint": NOMINATIM_URL,
        "raw_address": address,
        "normalized_address": entry.normalized_address,
        "cache_key": entry.cache_key,
        "previous_legacy_query": {"q": entry.normalized_address},
        "attempts": [
            {
                "variant": attempt.variant,
                "query": attempt.query,
                "http_status": attempt.http_status,
                "duration_ms": attempt.duration_ms,
                "result_count": attempt.result_count,
                "error_classification": attempt.error_classification,
                "rejection_reason": attempt.rejection_reason,
            }
            for attempt in resolution.attempts
        ],
        "final_precision": resolution.entry.precision if resolution.entry else None,
        "final_display_name": resolution.entry.display_name if resolution.entry else None,
        "final_warning": resolution.entry.warning if resolution.entry else None,
    }
    print(json.dumps({"probe": payload}, ensure_ascii=True, sort_keys=True))


def _run_atomic_address_chain(
    entries: tuple[GeoCacheEntry, ...],
    *,
    total_targets: int,
    raw_addresses: dict[str, str],
    output: Path,
) -> tuple[tuple[GeoCacheEntry, ...], OnlineLookupStatistics]:
    """One-process sequential chain; each completed cache entry is checkpointed atomically."""

    statistics = OnlineLookupStatistics(total_targets=total_targets)
    updated = list(entries)
    for index, entry in enumerate(updated):
        if entry.status == "resolved":
            statistics.cache_hit_resolved += 1
            continue
        if entry.geocode_attempted:
            statistics.cache_hit_unresolved += 1
            continue
        raw_address = raw_addresses[entry.cache_key]
        statistics.candidates_for_online_lookup += 1
        resolution = resolve_address_chain(
            entry,
            raw_address=raw_address,
            throttle_seconds=NOMINATIM_THROTTLE_SECONDS,
        )
        statistics.http_requests_sent += len(resolution.attempts)
        for attempt in resolution.attempts:
            if attempt.http_status is not None:
                statistics.http_statuses[attempt.http_status] += 1
            if attempt.error_classification is not None:
                statistics.exception_types[attempt.error_classification] += 1
            if attempt.rejection_reason is not None and attempt.rejection_reason != "no_match":
                statistics.exception_types[attempt.rejection_reason] += 1
        updated[index] = resolution.entry or unresolved_chain_entry(entry, resolution)
        _write_entries_atomic(output, tuple(updated))
    return tuple(updated), statistics


def _write_entries_atomic(path: Path, entries: tuple[GeoCacheEntry, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"entries": [entry.model_dump(mode="json") for entry in entries]}
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    temporary.replace(path)


def _load_entries(path: Path) -> tuple[GeoCacheEntry, ...]:
    if not path.is_file():
        return ()
    payload = json.loads(path.read_text(encoding="utf-8"))
    return tuple(GeoCacheEntry.model_validate(item) for item in payload["entries"])


if __name__ == "__main__":
    main()

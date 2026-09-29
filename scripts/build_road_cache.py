"""Explicit, sequential OSRM road-cache builder; never imported by runtime."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.models.geo import GeoCacheEntry
from app.models.road import GeoJsonLineString, RoadCache, RoadCacheEntry
from app.services.baseline import build_baseline_plan
from app.services.csv_loader import load_all_synthetic_sources
from app.services.enrichment import enrich_normalized_dataset
from app.services.geocache import build_offline_geodataset
from app.services.normalization import normalize_loaded_source_data
from app.services.optimizer import build_optimized_plan
from app.services.replan import build_replanned_plan
from app.services.workforce import build_workforce_dataset

OSRM_BASE = "https://router.project-osrm.org"
OUTPUT = PROJECT_ROOT / "data" / "generated" / "road_cache.json"
SOURCE_ROOT = PROJECT_ROOT.parent / "Датасет" / "Обезличивание"
THROTTLE_SECONDS = 1.0


def _write(path: Path, cache: RoadCache) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(cache.model_dump_json(indent=2), encoding="utf-8")
    temporary.replace(path)


def _request(path: str) -> dict:
    request = Request(
        f"{OSRM_BASE}{path}",
        headers={"User-Agent": "RouteFlow-hackathon-road-cache/1.0"},
    )
    with urlopen(request, timeout=45) as response:  # nosec B310 - explicit opt-in build only
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--online", action="store_true", help="Allow explicit OSRM requests."
    )
    parser.add_argument(
        "--territory",
        choices=("east", "southeast", "southcenter", "all"),
        default="east",
    )
    parser.add_argument(
        "--refresh", action="store_true", help="Refresh already resolved local entries."
    )
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    if not args.online:
        parser.error("--online is required; runtime never contacts OSRM")

    enriched = enrich_normalized_dataset(
        normalize_loaded_source_data(load_all_synthetic_sources(SOURCE_ROOT))
    )
    workforce = build_workforce_dataset(enriched)
    geo_path = PROJECT_ROOT / "data" / "generated" / "geocache.json"
    entries = tuple(
        GeoCacheEntry.model_validate(item)
        for item in json.loads(geo_path.read_text(encoding="utf-8"))["entries"]
    )
    dataset = build_offline_geodataset(enriched, workforce, entries)
    by_key = {entry.cache_key: entry for entry in dataset.entries}
    wanted = (
        {"east", "southeast", "southcenter"}
        if args.territory == "all"
        else {args.territory}
    )
    targets = [
        target
        for target in dataset.targets
        if target.target_kind == "office"
        or any(
            request.request_id == target.target_id and request.territory in wanted
            for request in enriched.requests
        )
        or target.target_id.startswith("event:")
    ]
    # Deduplicate coordinates/address keys: Table API is the controlled matrix request.
    targets = list(
        {
            target.cache_key: target
            for target in targets
            if by_key[target.cache_key].coordinates is not None
        }.values()
    )
    if args.output.exists():
        prior = RoadCache.model_validate_json(args.output.read_text(encoding="utf-8"))
    else:
        prior = RoadCache()
    prior_map = {
        (item.origin_cache_key, item.destination_cache_key): item
        for item in prior.entries
    }
    report = {
        "requests_sent": 0,
        "cache_hits": 0,
        "resolved": 0,
        "unresolved": 0,
        "warnings": [],
    }
    coordinates = ";".join(
        f"{by_key[target.cache_key].coordinates.longitude},{by_key[target.cache_key].coordinates.latitude}"
        for target in targets
    )
    try:
        table = _request(
            f"/table/v1/driving/{coordinates}?{urlencode({'annotations': 'distance,duration'})}"
        )
        report["requests_sent"] += 1
    except (
        HTTPError,
        URLError,
        TimeoutError,
        ValueError,
    ) as error:  # explicit report, never fabricate road data
        report["warnings"].append(f"OSRM table unavailable: {type(error).__name__}")
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return
    now = datetime.now(UTC)
    output = list(prior.entries)
    for origin_index, origin in enumerate(targets):
        for destination_index, destination in enumerate(targets):
            if origin.cache_key == destination.cache_key:
                continue
            key = (origin.cache_key, destination.cache_key)
            if (
                key in prior_map
                and prior_map[key].status == "resolved"
                and not args.refresh
            ):
                report["cache_hits"] += 1
                continue
            distance = table.get("distances", [[]])[origin_index][destination_index]
            duration = table.get("durations", [[]])[origin_index][destination_index]
            status = (
                "resolved"
                if distance is not None and duration is not None
                else "unresolved"
            )
            output = [
                item
                for item in output
                if (item.origin_cache_key, item.destination_cache_key) != key
            ]
            output.append(
                RoadCacheEntry(
                    origin_id=origin.target_id,
                    destination_id=destination.target_id,
                    origin_cache_key=origin.cache_key,
                    destination_cache_key=destination.cache_key,
                    distance_km=round(distance / 1000, 6)
                    if distance is not None
                    else None,
                    base_duration_min=int(-(-duration // 60))
                    if duration is not None
                    else None,
                    created_at=now,
                    status=status,
                    warning=None
                    if status == "resolved"
                    else "OSRM returned no road route.",
                )
            )
            report[status] += 1
    cache = RoadCache(
        entries=tuple(
            sorted(
                output,
                key=lambda item: (item.origin_cache_key, item.destination_cache_key),
            )
        )
    )
    _write(
        args.output,
        cache,
    )
    # Route API calls are strictly limited to car legs actually present in
    # final baseline/optimized/replan routes, never an engineer×request sweep.
    needed = _used_car_legs(enriched, workforce, dataset, cache, wanted)
    entry_map = {
        (item.origin_cache_key, item.destination_cache_key): item
        for item in cache.entries
    }
    for origin_key, destination_key in sorted(needed):
        current = entry_map.get((origin_key, destination_key))
        if (
            current is None
            or current.geometry is not None
            or current.status != "resolved"
        ):
            continue
        origin, destination = by_key[origin_key], by_key[destination_key]
        try:
            route = _request(
                f"/route/v1/driving/{origin.coordinates.longitude},{origin.coordinates.latitude};{destination.coordinates.longitude},{destination.coordinates.latitude}?{urlencode({'overview': 'full', 'geometries': 'geojson'})}"
            )
            geometry = GeoJsonLineString(
                coordinates=tuple(
                    (float(x), float(y))
                    for x, y in route["routes"][0]["geometry"]["coordinates"]
                )
            )
            entry_map[(origin_key, destination_key)] = current.model_copy(
                update={"geometry": geometry}
            )
            report["requests_sent"] += 1
            report["resolved"] += 1
        except (
            HTTPError,
            URLError,
            TimeoutError,
            ValueError,
            KeyError,
            IndexError,
        ) as error:
            report["warnings"].append(f"Geometry unavailable: {type(error).__name__}")
        time.sleep(THROTTLE_SECONDS)
    _write(
        args.output,
        RoadCache(
            entries=tuple(
                sorted(
                    entry_map.values(),
                    key=lambda item: (
                        item.origin_cache_key,
                        item.destination_cache_key,
                    ),
                )
            )
        ),
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


def _used_car_legs(enriched, workforce, geo, cache, territories):
    """Find finite, final car legs only; reserve is included only in its event plan."""
    engineers = {item.engineer_id: item for item in workforce.engineers}
    office_keys = {
        target.target_id: target.cache_key
        for target in geo.targets
        if target.target_kind == "office"
    }
    target_keys = {target.target_id: target.cache_key for target in geo.targets}
    plans = []
    for territory in sorted(territories):
        plans += [
            build_baseline_plan(enriched, workforce, geo, territory, "standard", cache),
            build_optimized_plan(
                enriched, workforce, geo, territory, "standard", cache
            ),
        ]
        plans += [
            build_replanned_plan(
                enriched, workforce, geo, event, "standard", cache
            ).replanned_plan
            for event in workforce.events
            if event.territory == territory
        ]
    pairs = set()
    for plan in plans:
        for route in plan.routes:
            engineer = engineers.get(route.engineer_id)
            is_car = (
                engineer is not None
                and engineer.available_transport == "car"
                or route.engineer_id.startswith("reserve-")
            )
            if not is_car:
                continue
            previous = office_keys[route.office_id]
            for stop in route.stops:
                destination = target_keys.get(stop.request_id) or next(
                    (
                        key
                        for ident, key in target_keys.items()
                        if ident.startswith("event:")
                    ),
                    None,
                )
                if destination:
                    pairs.add((previous, destination))
                    previous = destination
    return pairs


if __name__ == "__main__":
    main()

"""Run offline OR-Tools VRPTW plans for RouteFlow modes and traffic scenarios."""

from __future__ import annotations

import json
import sys
from argparse import ArgumentParser
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
WORKSPACE_ROOT = PROJECT_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.models.geo import GeoCacheEntry
from app.services.csv_loader import load_all_synthetic_sources
from app.services.enrichment import enrich_normalized_dataset
from app.services.geocache import build_offline_geodataset
from app.services.normalization import normalize_loaded_source_data
from app.services.optimizer import build_optimized_plan
from app.services.workforce import build_workforce_dataset


def main() -> None:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode", choices=("all", "east", "southeast", "southcenter"), default="all"
    )
    parser.add_argument(
        "--traffic-profile",
        choices=("standard", "moderate", "peak"),
        default="standard",
    )
    args = parser.parse_args()
    source_directory = WORKSPACE_ROOT / "Датасет" / "Обезличивание"
    cache_path = PROJECT_ROOT / "data" / "generated" / "geocache.json"
    enriched = enrich_normalized_dataset(
        normalize_loaded_source_data(load_all_synthetic_sources(source_directory))
    )
    workforce = build_workforce_dataset(enriched)
    entries = tuple(
        GeoCacheEntry.model_validate(item)
        for item in json.loads(cache_path.read_text(encoding="utf-8"))["entries"]
    )
    plan = build_optimized_plan(
        enriched,
        workforce,
        build_offline_geodataset(enriched, workforce, entries),
        args.mode,
        args.traffic_profile,
    )
    print(
        json.dumps(
            {
                "mode": plan.mode,
                "traffic_profile_id": plan.traffic_profile_id,
                "assigned": plan.assigned_count,
                "unassigned": plan.unassigned_count,
                "active_engineers": plan.active_engineer_count,
                "total_distance_km": plan.total_distance_km,
                "total_travel_minutes": plan.total_travel_minutes,
                "total_work_minutes": plan.total_work_minutes,
                "total_waiting_minutes": plan.total_waiting_minutes,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

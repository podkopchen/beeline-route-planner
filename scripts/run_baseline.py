"""Run the strict offline baseline for every supported territory mode."""

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
from app.services.baseline import (
    build_baseline_plan,
    unassigned_reason_counts,
)
from app.services.csv_loader import load_all_synthetic_sources
from app.services.enrichment import enrich_normalized_dataset
from app.services.geocache import build_offline_geodataset
from app.services.normalization import normalize_loaded_source_data
from app.services.workforce import build_workforce_dataset


def main() -> None:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--traffic-profile", default="standard")
    args = parser.parse_args()
    source_directory = WORKSPACE_ROOT / "Датасет" / "Обезличивание"
    cache_path = PROJECT_ROOT / "data" / "generated" / "geocache.json"
    enriched = enrich_normalized_dataset(
        normalize_loaded_source_data(load_all_synthetic_sources(source_directory))
    )
    workforce = build_workforce_dataset(enriched)
    cache_entries = tuple(
        GeoCacheEntry.model_validate(item)
        for item in json.loads(cache_path.read_text(encoding="utf-8"))["entries"]
    )
    geodataset = build_offline_geodataset(enriched, workforce, cache_entries)
    summary: dict[str, object] = {}
    for mode in ("all", "east", "southeast", "southcenter"):
        plan = build_baseline_plan(
            enriched, workforce, geodataset, mode, args.traffic_profile
        )
        summary[mode] = {
            "traffic_profile_id": plan.traffic_profile_id,
            "traffic_factor": plan.traffic_factor,
            "assigned": plan.assigned_count,
            "unassigned": plan.unassigned_count,
            "active_engineers": plan.active_engineer_count,
            "total_distance_km": plan.total_distance_km,
            "unassigned_reasons": dict(sorted(unassigned_reason_counts(plan).items())),
        }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

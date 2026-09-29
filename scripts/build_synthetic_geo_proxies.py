"""Offline-only GEO-001 completion for synthetic hackathon data."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.models.geo import GeoCacheEntry
from app.services.csv_loader import load_all_synthetic_sources
from app.services.enrichment import enrich_normalized_dataset
from app.services.geo_proxy import enrich_geodataset_with_proxies
from app.services.geocache import build_offline_geodataset
from app.services.normalization import normalize_loaded_source_data
from app.services.workforce import build_workforce_dataset

SOURCE_DIRECTORY = PROJECT_ROOT.parent / "\u0414\u0430\u0442\u0430\u0441\u0435\u0442" / "\u041e\u0431\u0435\u0437\u043b\u0438\u0447\u0438\u0432\u0430\u043d\u0438\u0435"
OUTPUT = PROJECT_ROOT / "data" / "generated" / "geocache.json"


def main() -> None:
    enriched = enrich_normalized_dataset(normalize_loaded_source_data(load_all_synthetic_sources(SOURCE_DIRECTORY)))
    workforce = build_workforce_dataset(enriched)
    payload = json.loads(OUTPUT.read_text(encoding="utf-8"))
    entries = tuple(GeoCacheEntry.model_validate(item) for item in payload["entries"])
    geodataset = build_offline_geodataset(enriched, workforce, entries)
    completed = enrich_geodataset_with_proxies(geodataset, enriched, workforce)
    temporary = OUTPUT.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps({"entries": [entry.model_dump(mode="json") for entry in completed.entries]}, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    temporary.replace(OUTPUT)
    print({"entries": len(completed.entries), "unresolved": sum(entry.status == "unresolved" for entry in completed.entries)})


if __name__ == "__main__":
    main()

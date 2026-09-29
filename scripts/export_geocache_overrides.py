"""Export unresolved GEO-001 entries as manual-coordinate override placeholders."""

from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CACHE_PATH = PROJECT_ROOT / "data" / "generated" / "geocache.json"
OUTPUT_PATH = PROJECT_ROOT / "data" / "generated" / "geocache_manual_overrides.template.json"


def main() -> None:
    payload = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    unresolved = [
        {
            "cache_key": entry["cache_key"],
            "normalized_address": entry["normalized_address"],
            "latitude": None,
            "longitude": None,
            "reason": entry["warning"] or "Manual verification required.",
        }
        for entry in payload["entries"]
        if entry["status"] != "resolved"
    ]
    OUTPUT_PATH.write_text(
        json.dumps({"overrides": unresolved}, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote {len(unresolved)} override placeholders to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

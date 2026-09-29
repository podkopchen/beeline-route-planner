"""Local deterministic migration of legacy warm cache into matrix and geometry files."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / "data/generated/road_cache.json"
MATRIX = ROOT / "data/generated/road_matrix_cache.json"
GEOMETRY = ROOT / "data/generated/road_geometry_cache.json"


def write(path: Path, payload: dict) -> None:
    temp = path.with_suffix(".tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    temp.replace(path)


def main() -> None:
    data = json.loads(LEGACY.read_text(encoding="utf-8"))
    matrix, geometry = [], []
    for entry in data["entries"]:
        item = {key: value for key, value in entry.items() if key != "geometry"}
        matrix.append(item)
        if entry.get("geometry") is not None:
            geometry.append(
                {
                    key: entry[key]
                    for key in ("origin_cache_key", "destination_cache_key", "geometry")
                }
            )
    write(MATRIX, {"version": 1, "entries": matrix})
    write(GEOMETRY, {"version": 1, "entries": geometry})
    print(
        json.dumps(
            {"matrix_entries": len(matrix), "geometry_entries": len(geometry)},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

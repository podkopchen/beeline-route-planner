"""Compact immutable road-cache indexes with lazy geometry loading."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from app.models.road import GeoJsonLineString, RoadCacheEntry


@dataclass(frozen=True, slots=True)
class RoadCacheStats:
    matrix_file_load_count: int
    geometry_file_load_count: int


class RoadCacheRepository:
    """One immutable parsed matrix per process; geometry remains unopened until needed."""

    def __init__(self, matrix_path: Path, geometry_path: Path) -> None:
        self.matrix_path, self.geometry_path = matrix_path, geometry_path
        self._matrix: dict[tuple[str, str], RoadCacheEntry] | None = None
        self._geometry: dict[tuple[str, str], GeoJsonLineString] | None = None
        self._matrix_loads = self._geometry_loads = 0
        self._lock = Lock()

    def lookup(self, origin_key: str, destination_key: str) -> RoadCacheEntry | None:
        self._ensure_matrix()
        assert self._matrix is not None
        return self._matrix.get((origin_key, destination_key))

    def geometry_for(
        self, origin_key: str, destination_key: str
    ) -> GeoJsonLineString | None:
        self._ensure_geometry()
        assert self._geometry is not None
        return self._geometry.get((origin_key, destination_key))

    def stats(self) -> RoadCacheStats:
        return RoadCacheStats(self._matrix_loads, self._geometry_loads)

    def _ensure_matrix(self) -> None:
        if self._matrix is not None:
            return
        with self._lock:
            if self._matrix is not None:
                return
            if not self.matrix_path.exists():
                self._matrix = {}
                return
            raw = json.loads(self.matrix_path.read_text(encoding="utf-8"))
            self._matrix = {
                (
                    item["origin_cache_key"],
                    item["destination_cache_key"],
                ): RoadCacheEntry.model_validate_json(
                    json.dumps({**item, "geometry": None})
                )
                for item in raw["entries"]
                if item["status"] == "resolved"
            }
            self._matrix_loads += 1

    def _ensure_geometry(self) -> None:
        if self._geometry is not None:
            return
        with self._lock:
            if self._geometry is not None:
                return
            if not self.geometry_path.exists():
                self._geometry = {}
                return
            raw = json.loads(self.geometry_path.read_text(encoding="utf-8"))
            self._geometry = {
                (
                    item["origin_cache_key"],
                    item["destination_cache_key"],
                ): GeoJsonLineString.model_validate_json(json.dumps(item["geometry"]))
                for item in raw["entries"]
            }
            self._geometry_loads += 1


_REPOSITORIES: dict[tuple[Path, int, Path, int], RoadCacheRepository] = {}
_GLOBAL_LOCK = Lock()


def road_cache_repository(
    matrix_path: Path, geometry_path: Path
) -> RoadCacheRepository:
    """Return the process singleton keyed by paths and mtimes; no data copying."""
    key = (
        matrix_path,
        matrix_path.stat().st_mtime_ns if matrix_path.exists() else -1,
        geometry_path,
        geometry_path.stat().st_mtime_ns if geometry_path.exists() else -1,
    )
    with _GLOBAL_LOCK:
        return _REPOSITORIES.setdefault(
            key, RoadCacheRepository(matrix_path, geometry_path)
        )

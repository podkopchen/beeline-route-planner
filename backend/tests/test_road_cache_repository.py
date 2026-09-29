import json
from pathlib import Path

from app.services.road_cache import road_cache_repository


def _files(tmp_path: Path):
    matrix = tmp_path / "matrix.json"
    geometry = tmp_path / "geometry.json"
    matrix.write_text(
        json.dumps(
            {
                "version": 1,
                "entries": [
                    {
                        "origin_id": "a",
                        "destination_id": "b",
                        "origin_cache_key": "a",
                        "destination_cache_key": "b",
                        "mode": "driving",
                        "distance_km": 5.5,
                        "base_duration_min": 14,
                        "source": "osrm",
                        "created_at": "2026-01-01T00:00:00Z",
                        "status": "resolved",
                        "warning": None,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    geometry.write_text(
        json.dumps(
            {
                "version": 1,
                "entries": [
                    {
                        "origin_cache_key": "a",
                        "destination_cache_key": "b",
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[37.5, 55.7], [37.6, 55.8]],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return matrix, geometry


def test_matrix_does_not_load_geometry_and_geometry_is_lazy(tmp_path):
    matrix, geometry = _files(tmp_path)
    cache = road_cache_repository(matrix, geometry)
    assert (
        cache.stats().matrix_file_load_count
        == cache.stats().geometry_file_load_count
        == 0
    )
    assert cache.lookup("a", "b").base_duration_min == 14
    assert (
        cache.stats().matrix_file_load_count == 1
        and cache.stats().geometry_file_load_count == 0
    )
    assert cache.geometry_for("a", "b").coordinates[0] == (37.5, 55.7)
    assert cache.stats().geometry_file_load_count == 1


def test_same_path_and_mtime_reuses_process_index(tmp_path):
    matrix, geometry = _files(tmp_path)
    assert road_cache_repository(matrix, geometry) is road_cache_repository(
        matrix, geometry
    )

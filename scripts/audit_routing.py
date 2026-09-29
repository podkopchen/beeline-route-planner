"""Read-only road coverage audit. Explicitly disables any configured HTTP provider."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.api.routes import _routes
from app.repositories.snapshots import RouteFlowSnapshotRepository


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--territory", choices=("all", "east", "southeast", "southcenter"), default="all")
    parser.add_argument("--traffic-profile", choices=("standard", "moderate", "peak"), default="standard")
    args = parser.parse_args()
    os.environ["ROUTEFLOW_ROUTING_MODE"] = "road_if_available"
    os.environ.pop("ROUTING_BASE_URL", None)
    repo = RouteFlowSnapshotRepository()
    snapshot = repo.plan("optimized", args.territory, args.traffic_profile)
    routes = _routes(snapshot, repo.inputs())
    report = {
        "mode": "road_if_available", "provider_disabled_for_audit": True,
        "traffic_profile": args.traffic_profile,
        "source_requests": len(repo.inputs().enriched.requests),
        "assigned": snapshot.plan.assigned_count,
        "coverage": dict(Counter(stop.geometry_status for route in routes for stop in route.stops)),
        "routes": [{"engineer": route.engineer_id, "territory": route.territory,
                    "visits": route.visit_count,
                    "coverage": dict(Counter(stop.geometry_status for stop in route.stops))}
                   for route in routes],
        "cache_loads": {
            "matrix": repo.inputs().road_cache.stats().matrix_file_load_count,
            "geometry": repo.inputs().road_cache.stats().geometry_file_load_count,
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

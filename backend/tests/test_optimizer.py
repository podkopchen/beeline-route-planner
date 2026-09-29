import json
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from app.models.geo import GeoCacheEntry
from app.services.baseline import build_baseline_plan
from app.services.csv_loader import load_all_synthetic_sources, permitted_source_paths
from app.services.enrichment import enrich_normalized_dataset
from app.services.geocache import build_offline_geodataset
from app.services.normalization import normalize_loaded_source_data
from app.services.optimizer import build_optimized_plan, objective_weights
from app.services.workforce import build_workforce_dataset

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = PROJECT_ROOT.parent
SOURCE_DIRECTORY = WORKSPACE_ROOT / "Датасет" / "Обезличивание"
CACHE_PATH = PROJECT_ROOT / "data" / "generated" / "geocache.json"


@pytest.fixture(scope="module")
def inputs():
    enriched = enrich_normalized_dataset(
        normalize_loaded_source_data(load_all_synthetic_sources(SOURCE_DIRECTORY))
    )
    workforce = build_workforce_dataset(enriched)
    entries = tuple(
        GeoCacheEntry.model_validate(item)
        for item in json.loads(CACHE_PATH.read_text(encoding="utf-8"))["entries"]
    )
    return enriched, workforce, build_offline_geodataset(enriched, workforce, entries)


def _scalar(dropped: int, active: int, distance: int, weights) -> int:
    return (
        dropped * weights.unassigned_request_penalty
        + active * weights.active_engineer_penalty
        + distance
    )


def test_objective_weights_prove_each_lexicographic_level() -> None:
    weights = objective_weights(distance_upper_bound_m=10, vehicle_count=2)
    assert _scalar(0, 2, 10, weights) < _scalar(1, 0, 0, weights)  # coverage
    assert _scalar(0, 1, 10, weights) < _scalar(0, 2, 0, weights)  # active engineers
    assert _scalar(0, 1, 9, weights) < _scalar(0, 1, 10, weights)  # distance


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("all", 205),
        ("east", 66),
        ("southeast", 83),
        ("southcenter", 56),
    ],
)
def test_optimized_routes_obey_hard_constraints_and_cover_the_selected_mode(
    inputs, mode, expected
) -> None:
    enriched, workforce, geodataset = inputs
    plan = build_optimized_plan(enriched, workforce, geodataset, mode, "standard")
    requests = {request.request_id: request for request in enriched.requests}
    engineers = {engineer.engineer_id: engineer for engineer in workforce.engineers}
    assigned = [stop.request_id for route in plan.routes for stop in route.stops]
    assert len(assigned) == len(set(assigned))
    assert plan.assigned_count + plan.unassigned_count == expected
    assert plan.unassigned_count == len(plan.unassigned)
    for route in plan.routes:
        engineer = engineers[route.engineer_id]
        assert route.total_distance_km == round(
            sum(stop.distance_from_previous_km for stop in route.stops), 6
        )
        assert len(route.stops) > 0  # no artificial office-return stop
        previous_end = engineer.shift_start
        for stop in route.stops:
            request = requests[stop.request_id]
            assert engineer.territory == request.territory == route.territory
            assert set(request.required_skills).issubset(engineer.skills)
            assert (
                request.transport_requirement == "none"
                or engineer.available_transport == "car"
            )
            assert stop.planned_arrival == previous_end + timedelta(
                minutes=stop.travel_from_previous_minutes
            )
            assert stop.service_start >= request.window_start
            assert stop.service_end <= request.window_end
            assert stop.service_end <= engineer.shift_end
            previous_end = stop.service_end


def test_profiles_are_deterministic_offline_and_never_worse_than_baseline(
    inputs,
) -> None:
    enriched, workforce, geodataset = inputs
    with patch(
        "socket.create_connection", side_effect=AssertionError("network called")
    ):
        standard = build_optimized_plan(
            enriched, workforce, geodataset, "all", "standard"
        )
        repeated = build_optimized_plan(
            enriched, workforce, geodataset, "all", "standard"
        )
        moderate = build_optimized_plan(
            enriched, workforce, geodataset, "all", "moderate"
        )
        peak = build_optimized_plan(enriched, workforce, geodataset, "all", "peak")
    assert standard == repeated
    for profile, plan in (
        ("standard", standard),
        ("moderate", moderate),
        ("peak", peak),
    ):
        baseline = build_baseline_plan(enriched, workforce, geodataset, "all", profile)
        assert plan.assigned_count >= baseline.assigned_count
        assert plan.traffic_profile_id == profile
    assert all(
        "Контрольное распределение" not in path.name
        for path in permitted_source_paths(SOURCE_DIRECTORY)
    )

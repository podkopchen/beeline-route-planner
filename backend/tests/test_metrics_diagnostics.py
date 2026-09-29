import json
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.models.geo import GeoCacheEntry
from app.services.baseline import build_baseline_plan
from app.services.csv_loader import load_all_synthetic_sources
from app.services.diagnostics import (
    DiagnosticInvariantError,
    _diagnose_request,
    diagnose_optimized_plan,
)
from app.services.enrichment import enrich_normalized_dataset
from app.services.geocache import build_offline_geodataset
from app.services.metrics import calculate_plan_metrics
from app.services.normalization import normalize_loaded_source_data
from app.services.optimizer import build_optimized_plan
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


def test_shared_metrics_match_both_builders_and_no_return_legs(inputs) -> None:
    enriched, workforce, geodataset = inputs
    baseline = build_baseline_plan(enriched, workforce, geodataset, "all", "standard")
    optimized = build_optimized_plan(enriched, workforce, geodataset, "all", "standard")
    assert baseline.metrics == calculate_plan_metrics(baseline, enriched, workforce)
    assert optimized.metrics == calculate_plan_metrics(optimized, enriched, workforce)
    assert baseline.metrics.distance_km == 735.449345
    assert baseline.metrics.travel_minutes == sum(
        route.total_travel_minutes for route in baseline.routes
    )
    assert (
        baseline.metrics.travel_minutes,
        baseline.metrics.service_minutes,
        baseline.metrics.waiting_minutes,
    ) == (1810, 4280, 11357)
    for route in optimized.metrics.routes:
        assert route.distance_km == round(
            sum(
                stop.distance_from_previous_km
                for stop in next(
                    item
                    for item in optimized.routes
                    if item.engineer_id == route.engineer_id
                ).stops
            ),
            6,
        )
        assert route.visit_count > 0


def test_diagnostics_are_one_per_unassigned_deterministic_and_profile_scoped(
    inputs,
) -> None:
    enriched, workforce, geodataset = inputs
    plans = {
        profile: build_optimized_plan(enriched, workforce, geodataset, "all", profile)
        for profile in ("standard", "moderate", "peak")
    }
    standard = plans["standard"]
    repeated = diagnose_optimized_plan(standard, enriched, workforce, geodataset)
    first = diagnose_optimized_plan(standard, enriched, workforce, geodataset)
    assert first == repeated
    assert len(first.diagnostics) == standard.unassigned_count
    assert {item.request_id for item in first.diagnostics} == {
        item.request_id for item in standard.unassigned
    }
    assert all(
        item.text_ru and item.scope and item.traffic_profile_id == "standard"
        for item in first.diagnostics
    )
    for profile, plan in plans.items():
        report = diagnose_optimized_plan(plan, enriched, workforce, geodataset)
        assert len(report.diagnostics) == plan.unassigned_count
        assert all(item.traffic_profile_id == profile for item in report.diagnostics)
        assert all(
            item.code != "final_plan_insertion_feasible" for item in report.diagnostics
        )
    insertion = next(
        item
        for item in first.diagnostics
        if item.code == "final_plan_insertion_infeasible"
    )
    assert insertion.standalone_feasible_engineer_count > 0
    assert insertion.checked_route_count > 0
    assert insertion.checked_route_positions >= insertion.checked_route_count
    assert "глобальная невозможность" in insertion.scope


def test_diagnostic_codes_follow_minimal_ordered_counterexamples(inputs) -> None:
    enriched, workforce, geodataset = inputs
    requests = {request.request_id: request for request in enriched.requests}
    entries = {entry.cache_key: entry for entry in geodataset.entries}
    offices = {
        office.office_id: entries[
            next(
                target.cache_key
                for target in geodataset.targets
                if target.target_id == office.office_id
            )
        ]
        for office in workforce.offices
    }
    plan = SimpleNamespace(traffic_profile_id="standard")
    network_request = next(
        request
        for request in enriched.requests
        if request.required_skills == ("network_repair",)
    )
    installation_engineer = next(
        engineer
        for engineer in workforce.engineers
        if engineer.territory == network_request.territory
        and "network_repair" not in engineer.skills
    )
    car_request = next(
        request
        for request in enriched.requests
        if request.transport_requirement == "car"
    )
    no_car_skill = next(
        engineer
        for engineer in workforce.engineers
        if engineer.territory == car_request.territory
        and set(car_request.required_skills).issubset(engineer.skills)
        and engineer.available_transport == "none"
    )
    empty_routes = {}
    assert (
        _diagnose_request(
            network_request, plan, (), requests, entries, offices, empty_routes
        ).code
        == "no_territory_engineer"
    )
    assert (
        _diagnose_request(
            network_request,
            plan,
            (installation_engineer,),
            requests,
            entries,
            offices,
            empty_routes,
        ).code
        == "skill_uncovered"
    )
    assert (
        _diagnose_request(
            car_request, plan, (no_car_skill,), requests, entries, offices, empty_routes
        ).code
        == "transport_uncovered"
    )
    tight = network_request.model_copy(
        update={"window_end": network_request.window_start + timedelta(minutes=1)}
    )
    eligible = next(
        engineer
        for engineer in workforce.engineers
        if engineer.territory == tight.territory
        and set(tight.required_skills).issubset(engineer.skills)
        and engineer.available_transport == "car"
    )
    assert (
        _diagnose_request(
            tight, plan, (eligible,), requests, entries, offices, empty_routes
        ).code
        == "window_shift_infeasible"
    )
    with pytest.raises(DiagnosticInvariantError, match="can be inserted"):
        _diagnose_request(
            network_request,
            plan,
            (eligible,),
            requests,
            entries,
            offices,
            empty_routes,
        )
    with patch(
        "socket.create_connection", side_effect=AssertionError("network called")
    ):
        assert diagnose_optimized_plan(
            build_optimized_plan(enriched, workforce, geodataset),
            enriched,
            workforce,
            geodataset,
        ).diagnostics

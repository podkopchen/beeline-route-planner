"""REPLAN-001.1 contract closure; no production behaviour is changed here."""

import asyncio
import socket

import httpx
import pytest

from app.main import create_app
from app.repositories.snapshots import RouteFlowSnapshotRepository


def _event_ids() -> tuple[str, ...]:
    return tuple(event.event_id for event in RouteFlowSnapshotRepository().inputs().workforce.events)


@pytest.mark.parametrize("event_id", _event_ids())
def test_all_catalogue_events_are_deterministic_and_keep_hard_constraints(event_id: str) -> None:
    repository = RouteFlowSnapshotRepository()
    first = repository.replan(event_id, "standard")
    second = repository.replan(event_id, "standard")
    assert first == second
    local_ids = {
        request.request_id for request in repository.inputs().enriched.requests
        if request.territory == first.event.territory
    }
    if first.event.event_type == "urgent_request":
        local_ids.add(first.event.payload.synthetic_request_id)
    expected_ids = local_ids - set(first.diff.cancelled_request_ids)
    assigned_ids = [stop.request_id for route in first.replanned_plan.routes for stop in route.stops]
    unassigned_ids = [item.request_id for item in first.replanned_plan.unassigned]
    assert len(assigned_ids) == len(set(assigned_ids))
    assert set(assigned_ids).isdisjoint(unassigned_ids)
    assert set(assigned_ids) | set(unassigned_ids) == expected_ids
    assert first.replanned_plan.assigned_count + first.replanned_plan.unassigned_count <= 206
    for route in first.replanned_plan.routes:
        assert tuple(stop.request_id for stop in route.stops) == tuple(dict.fromkeys(stop.request_id for stop in route.stops))
        assert all(stop.service_end >= stop.service_start for stop in route.stops)


def test_main_reserve_timing_committed_prefix_and_base_stability() -> None:
    repository = RouteFlowSnapshotRepository()
    result = repository.replan("event-east-urgent-1430", "standard")
    original = repository.plan("optimized", "east", "standard").plan
    reserve = next(route for route in result.replanned_plan.routes if route.engineer_id == "reserve-east-emergency-01")
    stop = reserve.stops[0]
    assert reserve.office_id == "office:east"
    assert (stop.distance_from_previous_km, stop.travel_from_previous_minutes) == pytest.approx((5.499936, 14))
    assert stop.planned_arrival.strftime("%H:%M") == "14:44"
    assert (stop.service_start.strftime("%H:%M"), stop.service_end.strftime("%H:%M")) == ("15:00", "16:20")
    assert result.diff.committed_visit_count == 29
    assert result.base_plan == original
    assert result.diff.activated_reserve_engineer_id == "reserve-east-emergency-01"


async def _post(path: str, payload: dict[str, str]) -> httpx.Response:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url="http://test") as client:
        return await client.post(path, json=payload)


@pytest.mark.parametrize("event_id", ("event-east-urgent-1430", "event-east-cancel-1300", "event-east-unavailable-1600"))
def test_replan_api_success_and_public_projection(event_id: str) -> None:
    response = asyncio.run(_post("/api/v1/replan", {"event_id": event_id, "traffic_profile": "standard"}))
    assert response.status_code == 200
    body = response.json()
    assert {"event", "replanned_plan", "diff", "outcome", "committed_stops"} == set(body)
    assert "objective_weights" not in body["replanned_plan"]


def test_replan_api_errors_and_no_socket(monkeypatch) -> None:
    monkeypatch.setattr(socket, "create_connection", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network")))
    assert asyncio.run(_post("/api/v1/replan", {"event_id": "unknown", "traffic_profile": "standard"})).status_code == 404
    assert asyncio.run(_post("/api/v1/replan", {"event_id": "event-east-urgent-1430", "traffic_profile": "unknown"})).status_code == 422

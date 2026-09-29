"""Routing provenance and future coordinate routing, without external requests."""

import asyncio
import socket
from types import SimpleNamespace

import httpx
import pytest

from app.api.routes import _routes
from app.main import create_app
from app.models.geo import Coordinates
from app.models.road import GeoJsonLineString
from app.repositories.snapshots import RouteFlowSnapshotRepository
from app.services.route_preview import CoordinateRouteRequest, build_coordinate_route
from app.services.routing import (
    OsrmHttpRoutingProvider,
    RoadRouteResult,
    RoutingUnavailableError,
)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.delenv("ROUTING_BASE_URL", raising=False)
    monkeypatch.setenv("ROUTEFLOW_ROUTING_MODE", "fallback_only")
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: pytest.fail("External network"))


def test_geometry_projection_preserves_provider_tuple_and_reports_noncar():
    repo = RouteFlowSnapshotRepository()
    snapshot = repo.plan("optimized", "east", "standard")
    route = snapshot.plan.routes[0]
    coordinates = ((37.5, 55.7), (37.6, 55.8))
    stop = route.stops[0].model_copy(update={"geometry": coordinates, "routing_source": "road"})
    plan = snapshot.plan.model_copy(update={"routes": (route.model_copy(update={"stops": (stop,)}),)})
    assert _routes(SimpleNamespace(plan=plan), repo.inputs())[0].stops[0].geometry == coordinates
    projected = _routes(snapshot, repo.inputs())
    none_ids = {eng.engineer_id for eng in repo.inputs().workforce.engineers if eng.available_transport == "none"}
    statuses = [s.geometry_status for r in projected if r.engineer_id in none_ids for s in r.stops]
    assert statuses and set(statuses) <= {"non_car_transport", "same_location"}


def test_urgent_geometry_uses_event_target_and_keeps_original_plan():
    repo = RouteFlowSnapshotRepository()
    inputs = repo.inputs()
    result = repo.replan("event-east-urgent-1430", "standard")
    reserve = next(r for r in result.replanned_plan.routes if r.engineer_id == "reserve-east-emergency-01")
    stop = reserve.stops[0]
    target = next(t for t in inputs.geodataset.targets if t.target_id == stop.request_id)
    office = next(t for t in inputs.geodataset.targets if t.target_id == reserve.office_id)
    calls = []
    geometry = GeoJsonLineString(coordinates=((37.5, 55.7), (37.6, 55.8)))
    cache = SimpleNamespace(geometry_for=lambda a, b: calls.append((a, b)) or geometry)
    projection_inputs = SimpleNamespace(geodataset=inputs.geodataset, workforce=inputs.workforce, road_cache=cache)
    original = result.replanned_plan.model_dump_json()
    road_reserve = reserve.model_copy(update={"stops": (stop.model_copy(update={"routing_source": "road", "geometry": None}),)})
    plan = result.replanned_plan.model_copy(update={"routes": (road_reserve,)})
    projected = _routes(SimpleNamespace(plan=plan), projection_inputs)
    assert calls == [(office.cache_key, target.cache_key)]
    assert projected[0].stops[0].geometry == geometry.coordinates
    assert result.replanned_plan.model_dump_json() == original


def test_cors_replan_preflight_and_readiness_are_honest():
    async def run():
        app = create_app()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.options("/api/v1/replan", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"})
            assert response.status_code == 200
            assert "POST" in response.headers["access-control-allow-methods"]
            rejected = await client.options("/api/v1/replan", headers={"Origin": "https://untrusted.invalid", "Access-Control-Request-Method": "POST"})
            assert rejected.status_code == 400
            status = (await client.get("/api/v1/routing/status")).json()
            assert status["input_requests"] == 205
            assert status["mode"] == "fallback_only"
            assert not status["provider_configured"] and not status["provider_checked"]
            assert not status["arbitrary_address_routing_ready"]
    asyncio.run(run())


@pytest.mark.parametrize("durations", [[[0, None], [2, 0]], [[0]], [[0, -1], [2, 0]], [[0, float("nan")], [2, 0]]])
def test_unusable_osrm_matrix_is_controlled(monkeypatch, durations):
    provider = OsrmHttpRoutingProvider("http://self-hosted.invalid")
    monkeypatch.setattr(provider, "_json", lambda path: {"code": "Ok", "durations": durations})
    points = (Coordinates(latitude=55.7, longitude=37.5), Coordinates(latitude=55.8, longitude=37.6))
    with pytest.raises(RoutingUnavailableError):
        provider.get_matrix(points)


def test_new_coordinate_route_requires_provider_and_rounds_only_once():
    a, b = Coordinates(latitude=55.7, longitude=37.5), Coordinates(latitude=55.8, longitude=37.6)
    request = CoordinateRouteRequest(points=(a, a, b, a, b), traffic_profile_id="moderate")
    with pytest.raises(RoutingUnavailableError):
        build_coordinate_route(request, None)
    class Provider:
        def __init__(self):
            self.calls = 0
        def get_route(self, origin, destination, profile="driving"):
            self.calls += 1
            return RoadRouteResult(1.0, 2, GeoJsonLineString(coordinates=((origin.longitude, origin.latitude), (destination.longitude, destination.latitude))), base_duration_seconds=61.0)
    provider = Provider()
    result = build_coordinate_route(request, provider)
    assert provider.calls == 2  # repeated directed leg memoized within this call
    assert result.legs[0].travel_minutes == 0 and result.legs[0].geometry is None
    assert result.distance_km == 3.0 and result.travel_minutes == 6
    assert result.legs[-1].destination == b  # no return added, input order retained
    assert result == build_coordinate_route(request, Provider())

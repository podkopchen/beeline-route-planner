import asyncio
import socket
from itertools import pairwise
from types import SimpleNamespace

import httpx

from app.main import create_app
from app.models.geo import Coordinates
from app.models.road import GeoJsonLineString
from app.repositories.snapshots import RouteFlowSnapshotRepository
from app.services.route_geometry import build_selected_route_geometry
from app.services.routing import OsrmHttpRoutingProvider, RoadRouteResult


def test_osrm_sequence_returns_one_shape_per_leg(monkeypatch):
    provider = OsrmHttpRoutingProvider("http://self-hosted.invalid")
    monkeypatch.setattr(
        provider,
        "_json",
        lambda _: {
            "code": "Ok",
            "routes": [
                {
                    "legs": [
                        {
                            "distance": 1200,
                            "duration": 125,
                            "steps": [
                                {"geometry": {"coordinates": [[37.5, 55.7], [37.55, 55.75]]}},
                                {"geometry": {"coordinates": [[37.55, 55.75], [37.6, 55.8]]}},
                            ],
                        },
                        {
                            "distance": 800,
                            "duration": 61,
                            "steps": [
                                {"geometry": {"coordinates": [[37.6, 55.8], [37.7, 55.9]]}}
                            ],
                        },
                    ]
                }
            ],
        },
    )
    result = provider.get_route_sequence(
        (
            Coordinates(latitude=55.7, longitude=37.5),
            Coordinates(latitude=55.8, longitude=37.6),
            Coordinates(latitude=55.9, longitude=37.7),
        )
    )
    assert len(result) == 2
    assert result[0].distance_km == 1.2
    assert result[0].base_duration_min == 3
    assert result[0].geometry.coordinates == (
        (37.5, 55.7),
        (37.55, 55.75),
        (37.6, 55.8),
    )


def test_selected_route_uses_one_provider_call_and_preserves_order():
    points = {
        "office": Coordinates(latitude=55.7, longitude=37.5),
        "one": Coordinates(latitude=55.8, longitude=37.6),
        "two": Coordinates(latitude=55.9, longitude=37.7),
    }
    inputs = SimpleNamespace(
        geodataset=SimpleNamespace(
            targets=(
                SimpleNamespace(target_id="office", cache_key="office"),
                SimpleNamespace(target_id="one", cache_key="one"),
                SimpleNamespace(target_id="two", cache_key="two"),
            ),
            entries=tuple(
                SimpleNamespace(cache_key=key, coordinates=value)
                for key, value in points.items()
            ),
        ),
        road_cache=SimpleNamespace(geometry_for=lambda *_: None),
    )
    route = SimpleNamespace(
        engineer_id="eng-1",
        office_id="office",
        stops=(SimpleNamespace(request_id="one"), SimpleNamespace(request_id="two")),
    )

    class Provider:
        calls = 0

        def get_route_sequence(self, route_points, profile="driving"):
            self.calls += 1
            return tuple(
                RoadRouteResult(
                    1.0,
                    2,
                    GeoJsonLineString(
                        coordinates=(
                            (origin.longitude, origin.latitude),
                            (destination.longitude, destination.latitude),
                        )
                    ),
                )
                for origin, destination in pairwise(route_points)
            )

    provider = Provider()
    result = build_selected_route_geometry(route, inputs, provider)
    assert provider.calls == 1
    assert [leg.request_id for leg in result.legs] == ["one", "two"]
    assert {leg.source for leg in result.legs} == {"on_demand"}

    # A complete warm cache must terminate successfully without a provider.
    geometry = GeoJsonLineString(coordinates=((37.5, 55.7), (37.6, 55.8)))
    inputs.road_cache = SimpleNamespace(geometry_for=lambda *_: geometry)
    cached = build_selected_route_geometry(route, inputs, None)
    assert cached.provider_request_count == 0
    assert len(cached.legs) == 2
    assert all(leg.geometry == geometry.coordinates for leg in cached.legs)


def test_api_builds_missing_geometry_once_without_mutating_plan(monkeypatch):
    monkeypatch.setenv("ROUTEFLOW_ROUTE_GEOMETRY_URL", "http://self-hosted.invalid")
    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("network")),
    )
    calls = 0

    def fake_sequence(_self, points, profile="driving"):
        nonlocal calls
        calls += 1
        return tuple(
            RoadRouteResult(
                1.0,
                2,
                GeoJsonLineString(
                    coordinates=(
                        (origin.longitude, origin.latitude),
                        (destination.longitude, destination.latitude),
                    )
                ),
            )
            for origin, destination in pairwise(points)
        )

    monkeypatch.setattr(OsrmHttpRoutingProvider, "get_route_sequence", fake_sequence)
    repository = RouteFlowSnapshotRepository()
    app = create_app(repository)

    async def run():
        before = repository.plan("optimized", "east", "standard").plan.model_dump_json()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            path = "/api/v1/plans/optimized/routes/eng-east-03/road-geometry?territory=east&traffic_profile=standard"
            first = await client.post(path)
            second = await client.post(path)
        assert first.status_code == 200
        assert first.json()["provider_request_count"] == 1
        assert all(leg["source"] == "on_demand" for leg in first.json()["legs"])
        assert second.json() == first.json()
        assert repository.plan("optimized", "east", "standard").plan.model_dump_json() == before

    asyncio.run(run())
    assert calls == 1

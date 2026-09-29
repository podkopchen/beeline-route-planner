"""ROUTE-001.1 routing modes; all providers are local mocks in this suite."""

from datetime import UTC, datetime

import pytest

from app.models.geo import Coordinates, GeoCacheEntry
from app.models.road import GeoJsonLineString, RoadCache, RoadCacheEntry
from app.services.routing import RoadRouteResult, RoutingUnavailableError
from app.services.travel import travel_metric


def _entry(key: str, longitude: float) -> GeoCacheEntry:
    return GeoCacheEntry(
        cache_key=key,
        normalized_address=key,
        coordinates=Coordinates(latitude=55.75, longitude=longitude),
        source="synthetic_proxy",
        geo_source="synthetic_proxy",
        status="resolved",
        warning=None,
        precision="synthetic_proxy",
        approximate=True,
    )


class Provider:
    def __init__(self) -> None:
        self.calls = 0

    def get_route(self, origin, destination, profile="driving"):
        self.calls += 1
        return RoadRouteResult(
            5.5,
            14,
            GeoJsonLineString(
                coordinates=(
                    (origin.longitude, origin.latitude),
                    (destination.longitude, destination.latitude),
                )
            ),
        )

    def get_matrix(self, points, profile="driving"):
        return ()


@pytest.mark.parametrize(
    "mode,source", [("fallback_only", "fallback"), ("road_if_available", "road")]
)
def test_routing_modes_are_explicit(mode, source):
    origin, destination, provider = _entry("a", 37.5), _entry("b", 37.6), Provider()
    metric = travel_metric(
        origin, destination, "car", RoadCache(), "moderate", mode, provider
    )
    assert metric.routing_source == source
    assert provider.calls == (0 if mode == "fallback_only" else 1)


def test_cache_hit_does_not_call_provider():
    origin, destination, provider = _entry("a", 37.5), _entry("b", 37.6), Provider()
    cache = RoadCache(
        entries=(
            RoadCacheEntry(
                origin_id="a",
                destination_id="b",
                origin_cache_key="a",
                destination_cache_key="b",
                distance_km=4.2,
                base_duration_min=11,
                geometry=GeoJsonLineString(coordinates=((37.5, 55.75), (37.6, 55.75))),
                created_at=datetime.now(UTC),
                status="resolved",
            ),
        )
    )
    assert (
        travel_metric(
            origin,
            destination,
            "car",
            cache,
            routing_mode="road_required",
            provider=provider,
        ).routing_source
        == "road"
    )
    assert provider.calls == 0


def test_required_mode_never_returns_fake_fallback_geometry():
    origin, destination = _entry("a", 37.5), _entry("b", 37.6)
    with pytest.raises(RoutingUnavailableError):
        travel_metric(
            origin, destination, "car", RoadCache(), routing_mode="road_required"
        )

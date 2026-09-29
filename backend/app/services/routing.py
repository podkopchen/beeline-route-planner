"""Production-facing road-routing provider contract.

Only this service layer may use a configured routing URL.  The default provider
is unavailable: the public OSRM demo server is intentionally not a runtime
dependency.
"""

from __future__ import annotations

import json
import math
import os
from collections.abc import Sequence
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.models.geo import Coordinates
from app.models.road import GeoJsonLineString, RoadCache, RoadCacheEntry


class RoadRouteResult:
    def __init__(
        self, distance_km: float, base_duration_min: int, geometry: GeoJsonLineString,
        base_duration_seconds: float | None = None,
    ) -> None:
        self.distance_km = distance_km
        self.base_duration_min = base_duration_min
        self.geometry = geometry
        self.base_duration_seconds = base_duration_seconds if base_duration_seconds is not None else base_duration_min * 60.0
        if not math.isfinite(distance_km) or distance_km < 0 or not math.isfinite(self.base_duration_seconds) or self.base_duration_seconds < 0:
            raise RoutingUnavailableError("routing_unavailable")


class RoutingUnavailableError(RuntimeError):
    """A controlled domain failure, never a fake straight road route."""


class RoutingProvider(Protocol):
    def get_matrix(
        self, points: Sequence[Coordinates], profile: str = "driving"
    ) -> tuple[tuple[float, ...], ...]: ...

    def get_route(
        self, origin: Coordinates, destination: Coordinates, profile: str = "driving"
    ) -> RoadRouteResult: ...

    def get_route_sequence(
        self, points: Sequence[Coordinates], profile: str = "driving"
    ) -> tuple[RoadRouteResult, ...]: ...


class CachedRoutingProvider:
    """First-level cache; it never performs I/O and never fabricates geometry."""

    def __init__(self, cache: RoadCache) -> None:
        self.cache = cache

    def lookup(self, origin_key: str, destination_key: str) -> RoadCacheEntry | None:
        return self.cache.lookup(origin_key, destination_key)


class UnavailableRoutingProvider:
    def get_matrix(
        self, points: Sequence[Coordinates], profile: str = "driving"
    ) -> tuple[tuple[float, ...], ...]:
        raise RoutingUnavailableError("routing_unavailable")

    def get_route(
        self, origin: Coordinates, destination: Coordinates, profile: str = "driving"
    ) -> RoadRouteResult:
        raise RoutingUnavailableError("routing_unavailable")

    def get_route_sequence(
        self, points: Sequence[Coordinates], profile: str = "driving"
    ) -> tuple[RoadRouteResult, ...]:
        raise RoutingUnavailableError("routing_unavailable")


class OsrmHttpRoutingProvider:
    """Configurable self-hosted OSRM adapter; no public URL default exists."""

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or os.getenv("ROUTING_BASE_URL", "")).rstrip("/")
        if not self.base_url:
            raise RoutingUnavailableError("routing_unavailable")

    def _json(self, path: str) -> dict:
        try:
            request = Request(
                f"{self.base_url}{path}", headers={"User-Agent": "RouteFlow/1.0"}
            )
            with urlopen(request, timeout=20) as response:  # nosec B310 - configured self-hosted endpoint
                payload = json.loads(response.read().decode("utf-8"))
                if not isinstance(payload, dict):
                    raise TypeError("Invalid OSRM object")
                return payload
        except (HTTPError, URLError, TimeoutError, TypeError, ValueError) as error:
            raise RoutingUnavailableError("routing_unavailable") from error

    def get_matrix(
        self, points: Sequence[Coordinates], profile: str = "driving"
    ) -> tuple[tuple[float, ...], ...]:
        if profile != "driving" or not points:
            raise RoutingUnavailableError("routing_unavailable")
        coordinates = ";".join(
            f"{point.longitude},{point.latitude}" for point in points
        )
        payload = self._json(
            f"/table/v1/{profile}/{coordinates}?{urlencode({'annotations': 'duration'})}"
        )
        try:
            durations = payload["durations"]
            if payload.get("code") != "Ok" or len(durations) != len(points):
                raise ValueError("Invalid matrix shape")
            result = tuple(tuple(float(value) for value in row) for row in durations)
            if any(len(row) != len(points) or any(not math.isfinite(value) or value < 0 for value in row) for row in result):
                raise ValueError("Invalid matrix value")
            return result  # OSRM seconds, not rounded planner minutes.
        except (KeyError, TypeError, ValueError, OverflowError) as error:
            raise RoutingUnavailableError("routing_unavailable") from error

    def get_route(
        self, origin: Coordinates, destination: Coordinates, profile: str = "driving"
    ) -> RoadRouteResult:
        if profile != "driving":
            raise RoutingUnavailableError("routing_unavailable")
        payload = self._json(
            f"/route/v1/{profile}/{origin.longitude},{origin.latitude};{destination.longitude},{destination.latitude}?{urlencode({'overview': 'full', 'geometries': 'geojson'})}"
        )
        try:
            if payload.get("code") != "Ok":
                raise ValueError("OSRM route unavailable")
            route = payload["routes"][0]
            return RoadRouteResult(
                round(float(route["distance"]) / 1000, 6),
                int(-(-float(route["duration"]) // 60)),
                GeoJsonLineString(
                    coordinates=tuple(
                        (float(x), float(y))
                        for x, y in route["geometry"]["coordinates"]
                    )
                ),
                base_duration_seconds=float(route["duration"]),
            )
        except (KeyError, IndexError, TypeError, ValueError, OverflowError) as error:
            raise RoutingUnavailableError("routing_unavailable") from error

    def get_route_sequence(
        self, points: Sequence[Coordinates], profile: str = "driving"
    ) -> tuple[RoadRouteResult, ...]:
        """Build every leg of one ordered route with a single OSRM request."""
        if profile != "driving" or len(points) < 2:
            raise RoutingUnavailableError("routing_unavailable")
        coordinates = ";".join(
            f"{point.longitude},{point.latitude}" for point in points
        )
        payload = self._json(
            f"/route/v1/{profile}/{coordinates}?"
            f"{urlencode({'overview': 'false', 'steps': 'true', 'geometries': 'geojson'})}"
        )
        try:
            if payload.get("code") != "Ok":
                raise ValueError("OSRM route unavailable")
            legs = payload["routes"][0]["legs"]
            if len(legs) != len(points) - 1:
                raise ValueError("Invalid route leg count")
            results = []
            for index, leg in enumerate(legs):
                geometry: list[tuple[float, float]] = []
                for step in leg["steps"]:
                    for raw in step["geometry"]["coordinates"]:
                        coordinate = (float(raw[0]), float(raw[1]))
                        if not geometry or geometry[-1] != coordinate:
                            geometry.append(coordinate)
                if len(geometry) < 2:
                    origin, destination = points[index], points[index + 1]
                    if origin != destination:
                        raise ValueError("OSRM leg geometry unavailable")
                    geometry = [
                        (origin.longitude, origin.latitude),
                        (destination.longitude, destination.latitude),
                    ]
                duration = float(leg["duration"])
                results.append(
                    RoadRouteResult(
                        distance_km=round(float(leg["distance"]) / 1000, 6),
                        base_duration_min=math.ceil(duration / 60),
                        base_duration_seconds=duration,
                        geometry=GeoJsonLineString(coordinates=tuple(geometry)),
                    )
                )
            return tuple(results)
        except (KeyError, IndexError, TypeError, ValueError, OverflowError) as error:
            raise RoutingUnavailableError("routing_unavailable") from error

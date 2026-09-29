"""Explicit, observable Nominatim lookups used only by the GEO build script."""

from __future__ import annotations

import json
import re
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field

from app.core.geo_config import NOMINATIM_URL, NOMINATIM_USER_AGENT
from app.models.geo import Coordinates, GeoCacheEntry, GeoQueryVariant

UrlOpener = Callable[..., object]
QueryParameters = dict[str, str | int]
MOSCOW_OBLAST_LATITUDE_RANGE = (54.0, 57.5)
MOSCOW_OBLAST_LONGITUDE_RANGE = (35.0, 41.5)
_ABBREVIATIONS = (
    (re.compile(r"(?<!\w)г\.?(?=\s)", re.IGNORECASE), "город"),
    (re.compile(r"(?<!\w)ул\.?(?=\s)", re.IGNORECASE), "улица"),
    (re.compile(r"(?<!\w)пр-?д\.?(?=\s)", re.IGNORECASE), "проезд"),
    (re.compile(r"(?<!\w)д\.?(?=\s)", re.IGNORECASE), "дом"),
    (re.compile(r"(?<!\w)с\.?(?=\s)", re.IGNORECASE), "строение"),
    (re.compile(r"(?<=\d)с\.?(?=\s)", re.IGNORECASE), "строение"),
)
_SPACES = re.compile(r"\s+")


@dataclass
class OnlineLookupStatistics:
    """Counters intentionally emitted by explicit online GEO operations."""

    total_targets: int
    cache_hit_resolved: int = 0
    cache_hit_unresolved: int = 0
    candidates_for_online_lookup: int = 0
    http_requests_sent: int = 0
    http_statuses: Counter[int] = field(default_factory=Counter)
    exception_types: Counter[str] = field(default_factory=Counter)

    def as_dict(self) -> dict[str, object]:
        return {
            "total_targets": self.total_targets,
            "cache_hit_resolved": self.cache_hit_resolved,
            "cache_hit_unresolved": self.cache_hit_unresolved,
            "candidates_for_online_lookup": self.candidates_for_online_lookup,
            "http_requests_sent": self.http_requests_sent,
            "http_statuses": dict(sorted(self.http_statuses.items())),
            "exception_types": dict(sorted(self.exception_types.items())),
        }


@dataclass(frozen=True)
class NominatimLookup:
    """Parsed result; neither response body nor credentials are retained."""

    http_status: int | None
    duration_ms: int
    matches: tuple[dict[str, object], ...]
    error_classification: str | None

    @property
    def result_count(self) -> int:
        return len(self.matches)


@dataclass(frozen=True)
class GeocodeAttempt:
    variant: GeoQueryVariant
    query: QueryParameters
    http_status: int | None
    duration_ms: int
    result_count: int
    error_classification: str | None
    rejection_reason: str | None


@dataclass(frozen=True)
class GeocodeResolution:
    entry: GeoCacheEntry | None
    attempts: tuple[GeocodeAttempt, ...]


def address_query_variants(
    raw_address: str,
) -> tuple[tuple[GeoQueryVariant, QueryParameters], ...]:
    """Build no more than three deterministic, increasingly constrained attempts."""

    raw_with_context = _with_moscow_russia(raw_address)
    normalized = expand_address_abbreviations(raw_address)
    normalized_with_context = _with_moscow_russia(normalized)
    street = _street_only(normalized)
    return (
        ("raw_freeform", _freeform_query(raw_with_context)),
        ("normalized_freeform", _freeform_query(normalized_with_context)),
        (
            "structured_street",
            {
                "street": street,
                "city": "Москва",
                "country": "Россия",
                "countrycodes": "ru",
                "format": "jsonv2",
                "limit": 1,
                "addressdetails": 1,
            },
        ),
    )


def expand_address_abbreviations(address: str) -> str:
    """Expand common Russian address abbreviations without changing their numbers."""

    expanded = address
    for pattern, replacement in _ABBREVIATIONS:
        expanded = pattern.sub(f"{replacement} ", expanded)
    expanded = re.sub(
        "(?<=\\d)(?=\\u0441\\u0442\\u0440\\u043e\\u0435\\u043d\\u0438\\u0435\\b)",
        " ",
        expanded,
    )
    return _SPACES.sub(" ", expanded).strip(" ,")


def resolve_address_chain(
    entry: GeoCacheEntry,
    *,
    raw_address: str,
    opener: UrlOpener = urllib.request.urlopen,
    throttle: Callable[[float], None] = time.sleep,
    throttle_seconds: float = 1.0,
) -> GeocodeResolution:
    """Resolve one address through max-three variants; street is the only fallback."""

    attempts: list[GeocodeAttempt] = []
    variants = address_query_variants(raw_address)
    for index, (variant, query) in enumerate(variants):
        lookup = lookup_nominatim_parameters(query, opener=opener)
        accepted, rejection = _acceptable_match(lookup.matches, variant)
        attempts.append(
            GeocodeAttempt(
                variant=variant,
                query=query,
                http_status=lookup.http_status,
                duration_ms=lookup.duration_ms,
                result_count=lookup.result_count,
                error_classification=lookup.error_classification,
                rejection_reason=rejection,
            )
        )
        if accepted is not None:
            precision = "street" if variant == "structured_street" else "house"
            warning = (
                "Concrete house was not found; coordinates are street-level only."
                if precision == "street"
                else None
            )
            return GeocodeResolution(
                entry=GeoCacheEntry(
                    cache_key=entry.cache_key,
                    normalized_address=entry.normalized_address,
                    coordinates=accepted["coordinates"],
                    source="nominatim",
                    status="resolved",
                    warning=warning,
                    query_variant=variant,
                    display_name=accepted["display_name"],
                    precision=precision,
                    approximate=precision == "street",
                    geocode_attempted=True,
                ),
                attempts=tuple(attempts),
            )
        if index < len(variants) - 1:
            throttle(throttle_seconds)
    return GeocodeResolution(entry=None, attempts=tuple(attempts))


def unresolved_chain_entry(
    entry: GeoCacheEntry, resolution: GeocodeResolution
) -> GeoCacheEntry:
    """Mark a completed chain so a resumed bulk run does not retry it silently."""

    final_reason = (
        resolution.attempts[-1].rejection_reason
        if resolution.attempts
        else "not_attempted"
    )
    return entry.model_copy(
        update={
            "warning": f"Nominatim chain unresolved: {final_reason}.",
            "geocode_attempted": True,
        }
    )


def resolve_unresolved_entries(
    entries: Iterable[GeoCacheEntry],
    *,
    total_targets: int,
    refresh_unresolved: bool,
    opener: UrlOpener = urllib.request.urlopen,
    throttle: Callable[[float], None] = time.sleep,
    throttle_seconds: float = 1.0,
) -> tuple[tuple[GeoCacheEntry, ...], OnlineLookupStatistics]:
    """Bulk mode retains the legacy single-query strategy and requires explicit refresh."""

    statistics = OnlineLookupStatistics(total_targets=total_targets)
    resolved_entries: list[GeoCacheEntry] = []
    for entry in entries:
        if entry.status == "resolved":
            statistics.cache_hit_resolved += 1
            resolved_entries.append(entry)
            continue
        if not refresh_unresolved or entry.normalized_address.startswith(
            "synthetic urgent"
        ):
            statistics.cache_hit_unresolved += 1
            resolved_entries.append(entry)
            continue
        statistics.candidates_for_online_lookup += 1
        lookup = lookup_nominatim(entry.normalized_address, opener=opener)
        _record_lookup(statistics, lookup)
        if lookup.http_status is not None or lookup.error_classification is not None:
            throttle(throttle_seconds)
        resolved_entries.append(_entry_from_lookup(entry, lookup))
    return tuple(resolved_entries), statistics


def probe_nominatim(
    address: str, *, opener: UrlOpener = urllib.request.urlopen
) -> NominatimLookup:
    """Legacy single-request probe kept for narrow connectivity checks."""

    return lookup_nominatim(address, opener=opener)


def lookup_nominatim(
    address: str, *, opener: UrlOpener = urllib.request.urlopen
) -> NominatimLookup:
    return lookup_nominatim_parameters(_freeform_query(address), opener=opener)


def lookup_nominatim_parameters(
    parameters: Mapping[str, str | int], *, opener: UrlOpener = urllib.request.urlopen
) -> NominatimLookup:
    """Perform one request and classify failures without logging request bodies."""

    request = urllib.request.Request(
        f"{NOMINATIM_URL}?{urllib.parse.urlencode(parameters)}",
        headers={"User-Agent": NOMINATIM_USER_AGENT},
    )
    started = time.perf_counter()
    try:
        with opener(request, timeout=20) as response:
            status = int(getattr(response, "status", response.getcode()))
            body = response.read()
    except (
        OSError,
        TimeoutError,
        ssl.SSLError,
        urllib.error.HTTPError,
        urllib.error.URLError,
    ) as error:
        return NominatimLookup(
            _http_status(error),
            _duration_ms(started),
            (),
            classify_nominatim_error(error),
        )
    if not 200 <= status < 300:
        return NominatimLookup(status, _duration_ms(started), (), f"http_{status}")
    if not body:
        return NominatimLookup(status, _duration_ms(started), (), "empty_response")
    try:
        payload = json.loads(body.decode("utf-8"))
        if not isinstance(payload, list) or not all(
            isinstance(item, dict) for item in payload
        ):
            raise ValueError("unexpected JSON shape")
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return NominatimLookup(status, _duration_ms(started), (), "parse_error")
    if not payload:
        return NominatimLookup(status, _duration_ms(started), (), "empty_result")
    return NominatimLookup(status, _duration_ms(started), tuple(payload), None)


def classify_nominatim_error(error: Exception) -> str:
    if isinstance(error, urllib.error.HTTPError):
        return f"http_{error.code}"
    if isinstance(error, (TimeoutError, socket.timeout)):
        return "timeout"
    if isinstance(error, ssl.SSLError):
        return "ssl"
    if isinstance(error, urllib.error.URLError):
        reason = error.reason
        if isinstance(reason, socket.gaierror):
            return "dns"
        if isinstance(reason, ssl.SSLError):
            return "ssl"
        if isinstance(reason, (TimeoutError, socket.timeout)):
            return "timeout"
        if "proxy" in str(reason).casefold() or "tunnel" in str(reason).casefold():
            return "proxy"
        return "url_error"
    return type(error).__name__


def _freeform_query(address: str) -> QueryParameters:
    return {"q": address, "format": "jsonv2", "limit": 1, "addressdetails": 1}


def _with_moscow_russia(address: str) -> str:
    result = address.strip(" ,")
    if "москва" not in result.casefold():
        result = f"{result}, Москва"
    if "россия" not in result.casefold():
        result = f"{result}, Россия"
    return result


def _street_only(normalized_address: str) -> str:
    without_city = re.sub(
        r"^город\s+москва\s*,?\s*", "", normalized_address, flags=re.IGNORECASE
    )
    street = without_city.split(",", maxsplit=1)[0].strip()
    if not street:
        raise ValueError("Address has no street component for structured fallback")
    return re.sub(r"^улица\s+", "", street, flags=re.IGNORECASE)


def _acceptable_match(
    matches: tuple[dict[str, object], ...], variant: GeoQueryVariant
) -> tuple[dict[str, object] | None, str | None]:
    if not matches:
        return None, "no_match"
    for match in matches:
        accepted, reason = _validate_match(match, variant)
        if accepted is not None:
            return accepted, None
    return None, reason


def _validate_match(
    match: dict[str, object], variant: GeoQueryVariant
) -> tuple[dict[str, object] | None, str]:
    address = match.get("address")
    if not isinstance(address, dict):
        return None, "missing_address_details"
    country_code = str(address.get("country_code", "")).casefold()
    country = str(address.get("country", "")).casefold()
    if country_code != "ru" or not ("рос" in country or "russia" in country):
        return None, "outside_russia"
    location = " ".join(
        str(address.get(key, ""))
        for key in ("city", "town", "village", "state", "region")
    ).casefold()
    if not ("москв" in location or "moscow" in location):
        return None, "outside_moscow_region"
    try:
        coordinates = Coordinates(
            latitude=float(match["lat"]), longitude=float(match["lon"])
        )
    except (KeyError, TypeError, ValueError):
        return None, "invalid_coordinates"
    if not (
        MOSCOW_OBLAST_LATITUDE_RANGE[0]
        <= coordinates.latitude
        <= MOSCOW_OBLAST_LATITUDE_RANGE[1]
        and MOSCOW_OBLAST_LONGITUDE_RANGE[0]
        <= coordinates.longitude
        <= MOSCOW_OBLAST_LONGITUDE_RANGE[1]
    ):
        return None, "coordinates_outside_moscow_region"
    if (
        variant != "structured_street"
        and not str(address.get("house_number", "")).strip()
    ):
        return None, "no_house_match"
    display_name = str(match.get("display_name", "")).strip()
    if not display_name:
        return None, "missing_display_name"
    return {"coordinates": coordinates, "display_name": display_name}, ""


def _record_lookup(statistics: OnlineLookupStatistics, lookup: NominatimLookup) -> None:
    statistics.http_requests_sent += 1
    if lookup.http_status is not None:
        statistics.http_statuses[lookup.http_status] += 1
    if lookup.error_classification is not None:
        statistics.exception_types[lookup.error_classification] += 1


def _entry_from_lookup(entry: GeoCacheEntry, lookup: NominatimLookup) -> GeoCacheEntry:
    if lookup.error_classification is not None:
        return entry.model_copy(
            update={
                "warning": f"Nominatim lookup failed: {lookup.error_classification}."
            }
        )
    if not lookup.matches:
        return entry.model_copy(update={"warning": "Nominatim returned no match."})
    match = lookup.matches[0]
    try:
        coordinates = Coordinates(
            latitude=float(match["lat"]), longitude=float(match["lon"])
        )
    except (KeyError, TypeError, ValueError):
        return entry.model_copy(
            update={"warning": "Nominatim lookup failed: parse_error."}
        )
    return entry.model_copy(
        update={
            "coordinates": coordinates,
            "source": "nominatim",
            "status": "resolved",
            "warning": None,
        }
    )


def _http_status(error: Exception) -> int | None:
    return error.code if isinstance(error, urllib.error.HTTPError) else None


def _duration_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)

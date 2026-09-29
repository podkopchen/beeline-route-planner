import json
from collections.abc import Iterator
from typing import Self
from urllib.parse import parse_qs, urlparse

from app.models.geo import GeoCacheEntry
from app.services.geocache import UNRESOLVED_WARNING
from app.services.nominatim import (
    address_query_variants,
    expand_address_abbreviations,
    resolve_address_chain,
    resolve_unresolved_entries,
)

RAW_OFFICE = "\u0433. \u041c\u043e\u0441\u043a\u0432\u0430, \u0443\u043b \u042e\u043d\u044b\u0445 \u041b\u0435\u043d\u0438\u043d\u0446\u0435\u0432, \u0434 83\u0441 4"


def _unresolved(key: str = "unresolved-key") -> GeoCacheEntry:
    return GeoCacheEntry(
        cache_key=key,
        normalized_address="\u043c\u043e\u0441\u043a\u0432\u0430 \u0443\u043b\u0438\u0446\u0430 \u0442\u0435\u0441\u0442\u043e\u0432\u0430\u044f 1",
        coordinates=None,
        source="unresolved",
        status="unresolved",
        warning=UNRESOLVED_WARNING,
    )


def _match(*, country_code: str = "ru", state: str = "\u041c\u043e\u0441\u043a\u0432\u0430", house: str | None = "83") -> dict[str, object]:
    address: dict[str, object] = {
        "country_code": country_code,
        "country": "\u0420\u043e\u0441\u0441\u0438\u044f" if country_code == "ru" else "Polska",
        "city": "\u041c\u043e\u0441\u043a\u0432\u0430",
        "state": state,
    }
    if house is not None:
        address["house_number"] = house
    return {
        "lat": "55.7000",
        "lon": "37.7600",
        "display_name": "\u0443\u043b\u0438\u0446\u0430 \u042e\u043d\u044b\u0445 \u041b\u0435\u043d\u0438\u043d\u0446\u0435\u0432, 83, \u041c\u043e\u0441\u043a\u0432\u0430, \u0420\u043e\u0441\u0441\u0438\u044f",
        "address": address,
    }


class _Response:
    status = 200

    def __init__(self, payload: list[dict[str, object]]) -> None:
        self.payload = payload

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def getcode(self) -> int:
        return 200

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def _opener(responses: list[list[dict[str, object]]], calls: list[dict[str, list[str]]]) -> object:
    iterator: Iterator[list[dict[str, object]]] = iter(responses)

    def open_request(request: object, **_kwargs: object) -> _Response:
        calls.append(parse_qs(urlparse(str(request.full_url)).query))
        return _Response(next(iterator))

    return open_request


def test_expands_common_abbreviations_without_losing_house_or_building() -> None:
    assert expand_address_abbreviations(RAW_OFFICE) == (
        "\u0433\u043e\u0440\u043e\u0434 \u041c\u043e\u0441\u043a\u0432\u0430, "
        "\u0443\u043b\u0438\u0446\u0430 \u042e\u043d\u044b\u0445 \u041b\u0435\u043d\u0438\u043d\u0446\u0435\u0432, "
        "\u0434\u043e\u043c 83 \u0441\u0442\u0440\u043e\u0435\u043d\u0438\u0435 4"
    )


def test_house_level_match_is_accepted_on_first_freeform_variant() -> None:
    calls: list[dict[str, list[str]]] = []
    resolution = resolve_address_chain(
        _unresolved(),
        raw_address=RAW_OFFICE,
        opener=_opener([[_match()]], calls),
        throttle=lambda _seconds: None,
    )

    assert resolution.entry is not None
    assert resolution.entry.precision == "house"
    assert resolution.entry.approximate is False
    assert resolution.entry.query_variant == "raw_freeform"
    assert resolution.entry.warning is None
    assert len(calls) == 1
    assert calls[0]["q"][0].endswith("\u0420\u043e\u0441\u0441\u0438\u044f")


def test_empty_freeform_queries_transition_to_structured_street_fallback() -> None:
    calls: list[dict[str, list[str]]] = []
    resolution = resolve_address_chain(
        _unresolved(),
        raw_address=RAW_OFFICE,
        opener=_opener([[], [], [_match(house=None)]], calls),
        throttle=lambda _seconds: None,
    )

    assert resolution.entry is not None
    assert resolution.entry.precision == "street"
    assert resolution.entry.approximate is True
    assert resolution.entry.query_variant == "structured_street"
    assert resolution.entry.warning is not None
    assert len(calls) == 3
    assert calls[2]["street"] == ["\u042e\u043d\u044b\u0445 \u041b\u0435\u043d\u0438\u043d\u0446\u0435\u0432"]
    assert calls[2]["city"] == ["\u041c\u043e\u0441\u043a\u0432\u0430"]
    assert calls[2]["countrycodes"] == ["ru"]


def test_result_from_another_country_is_rejected_and_never_resolved() -> None:
    calls: list[dict[str, list[str]]] = []
    foreign = _match(country_code="pl")
    resolution = resolve_address_chain(
        _unresolved(),
        raw_address=RAW_OFFICE,
        opener=_opener([[foreign], [foreign], [foreign]], calls),
        throttle=lambda _seconds: None,
    )

    assert resolution.entry is None
    assert len(calls) == 3
    assert all(attempt.rejection_reason == "outside_russia" for attempt in resolution.attempts)


def test_query_variants_are_pure_and_do_not_make_network_calls() -> None:
    variants = address_query_variants(RAW_OFFICE)

    assert len(variants) == 3
    assert variants[2][1]["countrycodes"] == "ru"


def test_online_mode_keeps_cached_unresolved_until_explicit_refresh() -> None:
    def unexpected_network(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("cached unresolved must not trigger an implicit lookup")

    entries, statistics = resolve_unresolved_entries(
        (_unresolved(),), total_targets=1, refresh_unresolved=False, opener=unexpected_network
    )

    assert entries == (_unresolved(),)
    assert statistics.cache_hit_unresolved == 1
    assert statistics.candidates_for_online_lookup == 0
    assert statistics.http_requests_sent == 0

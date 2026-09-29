from datetime import datetime
from zoneinfo import ZoneInfo

from app.models.enriched_dataset import EnrichedDataset, EnrichedRequest
from app.models.geo import Coordinates, GeoCacheEntry, GeoDataset
from app.models.normalized_dataset import NormalizedOffice
from app.models.workforce import Engineer, WorkforceDataset
from app.services.baseline import build_baseline_plan
from app.services.geocache import geocache_key

MSK = ZoneInfo("Europe/Moscow")


def _time(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 1, 15, hour, minute, tzinfo=MSK)


def _office(
    territory: str = "east", address: str = "Москва, Тестовая улица, 1"
) -> NormalizedOffice:
    return NormalizedOffice(
        office_id=f"office:{territory}",
        territory=territory,
        source_filename="fixture.csv",
        source_line=2,
        source_address=address,
    )


def _request(
    request_id: str,
    order: int,
    address: str,
    *,
    territory: str = "east",
    skill: str = "installation",
    transport: str = "none",
    start: int = 9,
    end: int = 18,
    duration: int = 30,
) -> EnrichedRequest:
    return EnrichedRequest(
        request_id=request_id,
        source_request_id=request_id,
        source_order=order,
        source_line=order + 2,
        territory=territory,
        source_filename="fixture.csv",
        source_address=address,
        district="",
        bk_request_type="",
        hd_request_type="",
        gigabit_connection="",
        connection=None,
        window_start=_time(start),
        window_end=_time(end),
        source_fields={},
        required_skills=(skill,),
        complexity="low",
        normative_work_name="Fixture normative",
        technical_work_min=duration,
        documents_min=0,
        service_duration_min=duration,
        normative_travel_min=20,
        base_normative_min=duration + 20,
        priority="normal",
        transport_requirement=transport,
    )


def _engineer(
    engineer_id: str,
    *,
    territory: str = "east",
    skills: tuple[str, ...] = ("installation",),
    transport: str = "none",
    shift_end: int = 18,
) -> Engineer:
    return Engineer(
        engineer_id=engineer_id,
        territory=territory,
        office_id=f"office:{territory}",
        shift_start=_time(8),
        shift_end=_time(shift_end),
        skills=skills,
        available_transport=transport,
        level="middle",
    )


def _entry(address: str, latitude: float, longitude: float) -> GeoCacheEntry:
    return GeoCacheEntry(
        cache_key=geocache_key(address),
        normalized_address=address.casefold(),
        coordinates=Coordinates(latitude=latitude, longitude=longitude),
        source="nominatim",
        geo_source="nominatim",
        status="resolved",
        warning=None,
        precision="house",
        approximate=False,
    )


def _plan(
    requests: tuple[EnrichedRequest, ...],
    engineers: tuple[Engineer, ...],
    offices: tuple[NormalizedOffice, ...],
    entries: tuple[GeoCacheEntry, ...],
    mode: str = "east",
):
    enriched = EnrichedDataset(enrichment_seed=2026, requests=requests, offices=offices)
    workforce = WorkforceDataset(
        workforce_seed=2026, engineers=engineers, offices=offices, events=()
    )
    return build_baseline_plan(
        enriched, workforce, GeoDataset(entries=entries, targets=()), mode
    )


def test_source_order_first_feasible_and_waiting_are_preserved() -> None:
    office = _office()
    first = _request("r-1", 0, "Москва, Улица Один, 1", start=10)
    second = _request("r-2", 1, "Москва, Улица Два, 1")
    plan = _plan(
        (second, first),
        (_engineer("eng-first"), _engineer("eng-closer")),
        (office,),
        (
            _entry(office.source_address, 55.75, 37.60),
            _entry(first.source_address, 55.76, 37.61),
            _entry(second.source_address, 55.77, 37.62),
        ),
    )
    assert [item.request_id for item in plan.assignments] == ["r-1", "r-2"]
    assert [item.engineer_id for item in plan.assignments] == ["eng-first", "eng-first"]
    stops = plan.routes[0].stops
    assert stops[0].waiting_minutes > 0
    assert stops[0].service_start == first.window_start
    assert len(stops) == 2  # no appended office-return stop
    assert stops[1].previous_cache_key == geocache_key(first.source_address)


def test_skill_transport_and_route_timing_are_hard_constraints() -> None:
    office = _office()
    no_skill = _request("no-skill", 0, "Москва, А, 1", skill="network_repair")
    needs_car = _request("needs-car", 1, "Москва, Б, 1", transport="car")
    tight = _request("tight", 2, "Москва, В, 1", start=8, end=9, duration=30)
    plan = _plan(
        (no_skill, needs_car, tight),
        (_engineer("eng"),),
        (office,),
        (
            _entry(office.source_address, 55.75, 37.60),
            _entry(no_skill.source_address, 55.76, 37.61),
            _entry(needs_car.source_address, 55.76, 37.61),
            _entry(tight.source_address, 55.90, 37.90),
        ),
    )
    assert [item.code for item in plan.unassigned] == [
        "no_skill_candidate",
        "no_transport_candidate",
        "time_route_infeasible",
    ]


def test_previous_stop_changes_engineer_availability() -> None:
    office = _office()
    first = _request("first", 0, "Москва, Первое, 1", start=9, end=10, duration=30)
    second = _request("second", 1, "Москва, Второе, 1", start=9, end=10, duration=30)
    plan = _plan(
        (first, second),
        (_engineer("eng"),),
        (office,),
        (
            _entry(office.source_address, 55.75, 37.60),
            _entry(first.source_address, 55.75, 37.60),
            _entry(second.source_address, 55.90, 37.90),
        ),
    )
    assert [item.request_id for item in plan.assignments] == ["first"]
    assert plan.unassigned[0].code == "time_route_infeasible"


def test_all_mode_uses_fixed_territory_file_order() -> None:
    east_office, southeast_office = (
        _office("east"),
        _office("southeast", "Москва, ЮВ офис, 1"),
    )
    east = _request("east", 8, "Москва, Восток, 1", territory="east")
    southeast = _request("southeast", 0, "Москва, ЮВ, 1", territory="southeast")
    plan = _plan(
        (southeast, east),
        (_engineer("east-eng"), _engineer("se-eng", territory="southeast")),
        (east_office, southeast_office),
        (
            _entry(east_office.source_address, 55.7, 37.6),
            _entry(southeast_office.source_address, 55.7, 37.6),
            _entry(east.source_address, 55.71, 37.61),
            _entry(southeast.source_address, 55.72, 37.62),
        ),
        "all",
    )
    assert [item.request_id for item in plan.assignments] == ["east", "southeast"]
    assert [
        stop.global_source_order for route in plan.routes for stop in route.stops
    ] == [0, 1]

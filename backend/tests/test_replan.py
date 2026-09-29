"""Regression evidence for the currently blocked East urgent scenario."""

from app.repositories.snapshots import RouteFlowSnapshotRepository
from app.services.workforce import MAIN_REPLAN_EVENT_ID


def test_east_urgent_activates_the_synthetic_emergency_reserve() -> None:
    repository = RouteFlowSnapshotRepository()
    result = repository.replan(MAIN_REPLAN_EVENT_ID, "standard")

    assert result.event.payload.service_duration_min == 80
    assert result.outcome.status == "applied"
    assert result.diff.committed_visit_count == 29
    assert result.base_plan.assigned_count == 54
    reserve_route = next(route for route in result.replanned_plan.routes if route.engineer_id == "reserve-east-emergency-01")
    stop = reserve_route.stops[0]
    assert reserve_route.office_id == "office:east"
    assert stop.request_id == "event-urgent-east-001"
    assert stop.travel_from_previous_minutes == 14
    assert stop.service_start.strftime("%H:%M") == "15:00"
    assert stop.service_end.strftime("%H:%M") == "16:20"
    assert result.diff.emergency_reserve_activated is True
    assert result.diff.activated_reserve_engineer_id == reserve_route.engineer_id


def test_non_urgent_events_do_not_activate_reserve() -> None:
    repository = RouteFlowSnapshotRepository()
    for event_id in ("event-east-cancel-1300", "event-east-unavailable-1600"):
        result = repository.replan(event_id, "standard")
        assert result.diff.emergency_reserve_activated is False
        assert all(not route.engineer_id.startswith("reserve-") for route in result.replanned_plan.routes)

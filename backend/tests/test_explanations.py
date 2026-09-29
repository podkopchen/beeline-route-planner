import asyncio
import socket

import httpx

from app.main import create_app
from app.repositories.snapshots import RouteFlowSnapshotRepository
from app.services.explanations import explain_request


def test_assigned_and_unassigned_canonical_explanations_are_plan_evidence() -> None:
    repository = RouteFlowSnapshotRepository()
    inputs = repository.inputs()
    snapshot = repository.plan("optimized", "all", "standard")
    assigned_id = snapshot.plan.routes[0].stops[0].request_id
    assigned = explain_request(
        next(x for x in inputs.enriched.requests if x.request_id == assigned_id),
        snapshot.plan,
        inputs.workforce,
        "optimized",
    )
    assert assigned.status == "assigned" and any(
        fact.key == "engineer_id" for fact in assigned.facts
    )
    diagnostic = snapshot.diagnostics.diagnostics[0]
    unassigned = explain_request(
        next(
            x for x in inputs.enriched.requests if x.request_id == diagnostic.request_id
        ),
        snapshot.plan,
        inputs.workforce,
        "optimized",
        diagnostic,
    )
    assert (
        unassigned.status == "unassigned"
        and "final_plan_insertion_feasible" not in unassigned.model_dump_json()
    )
    if diagnostic.code == "final_plan_insertion_infeasible":
        assert "глобальная" in unassigned.evidence_scope


async def _get(path: str) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        return await client.get(path)


def test_explanation_api_and_urgent_reserve_are_public_facts(monkeypatch) -> None:
    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network")),
    )
    urgent = asyncio.run(
        _get(
            "/api/v1/requests/event-urgent-east-001/explanation?event_id=event-east-urgent-1430"
        )
    ).json()
    assert (
        urgent["status"] == "assigned"
        and urgent["event_id"] == "event-east-urgent-1430"
    )
    assert any(fact["value"] == "reserve-east-emergency-01" for fact in urgent["facts"])
    assert asyncio.run(_get("/api/v1/requests/nope/explanation")).status_code == 404
    assert (
        asyncio.run(
            _get(
                "/api/v1/requests/east:74198/explanation?event_id=event-southeast-cancel-1300"
            )
        ).status_code
        == 422
    )

import asyncio
import socket

import httpx

from app.main import create_app


async def _get(path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path)

def get(path: str) -> httpx.Response:
    return asyncio.run(_get(path))

def test_read_only_api_contract_and_no_socket(monkeypatch) -> None:
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    health = get("/health").json()
    assert health == {"status": "ok", "api_version": "1.0.0", "offline": True}
    territories = get("/api/v1/territories").json()
    assert [x["engineer_count"] for x in territories] == [12, 12, 11]
    assert get("/api/v1/events").status_code == 200 and len(get("/api/v1/events").json()) == 9
    assert len(get("/api/v1/engineers").json()) == 35
    page, next_page = get("/api/v1/requests?limit=10&offset=0").json(), get("/api/v1/requests?limit=10&offset=10").json()
    assert page["total"] == 205 and not ({x["request_id"] for x in page["items"]} & {x["request_id"] for x in next_page["items"]})
    unassigned = get("/api/v1/requests?assignment_status=unassigned&limit=205").json()
    assert unassigned["total"] == 48 and {item["assignment_status"] for item in unassigned["items"]} == {"unassigned"}

def test_plan_totals_diagnostics_errors_and_openapi() -> None:
    baseline, optimized = get("/api/v1/summary?plan_kind=baseline").json(), get("/api/v1/plans/optimized").json()
    assert (baseline["assigned_count"], baseline["unassigned_count"], baseline["active_engineer_count"]) == (92, 113, 31)
    assert (optimized["summary"]["assigned_count"], optimized["summary"]["unassigned_count"], optimized["summary"]["active_engineer_count"]) == (157, 48, 25)
    assert len(optimized["unassigned_diagnostics"]) == 48
    assert set(optimized["unassigned_request_ids"]) == {item["request_id"] for item in get("/api/v1/requests?assignment_status=unassigned&limit=205").json()["items"]}
    assert "final_plan_insertion_feasible" not in {x["code"] for x in optimized["unassigned_diagnostics"]}
    assert get("/api/v1/summary?traffic_profile=nope").status_code == 422
    assert get("/api/v1/requests/nope").status_code == 404
    assert "/api/v1/plans/{plan_kind}" in get("/openapi.json").json()["paths"]

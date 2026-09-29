import asyncio

import httpx

from app.main import app


def test_healthcheck_is_available_without_product_data() -> None:
    async def request_healthcheck() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://routeflow.test",
        ) as client:
            return await client.get("/api/health")

    response = asyncio.run(request_healthcheck())

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "stage": "infrastructure"}

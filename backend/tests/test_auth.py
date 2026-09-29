import asyncio

import httpx

from app.core.auth_config import auth_config
from app.main import create_app
from app.services.auth import AuthUser, issue_session, read_session


def configure_auth(monkeypatch):
    monkeypatch.setenv("ROUTEFLOW_AUTH_ENABLED", "true")
    monkeypatch.setenv("ROUTEFLOW_DEMO_USERNAME", "dispatcher")
    monkeypatch.setenv("ROUTEFLOW_DEMO_PASSWORD", "test-password")
    monkeypatch.setenv("ROUTEFLOW_SESSION_SECRET", "x" * 48)


def test_auth_cors_preflight_and_unauthorized_response(monkeypatch):
    configure_auth(monkeypatch)
    app = create_app()

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://localhost"
        ) as client:
            origin = "http://localhost:5173"
            response = await client.options("/api/v1/replan", headers={
                "Origin": origin, "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            })
            assert response.status_code == 200
            assert response.headers["access-control-allow-origin"] == origin
            rejected = await client.get("/api/v1/territories", headers={"Origin": origin})
            assert rejected.status_code == 401
            assert rejected.headers["access-control-allow-origin"] == origin
            foreign = await client.options("/api/v1/replan", headers={
                "Origin": "https://untrusted.invalid", "Access-Control-Request-Method": "POST",
            })
            assert foreign.status_code == 400
            assert "access-control-allow-origin" not in foreign.headers

    asyncio.run(run())


def test_signed_session_rejects_tampering_and_expiry(monkeypatch):
    configure_auth(monkeypatch)
    config = auth_config()
    user = AuthUser("dispatcher", "Диспетчер смены", "dispatcher")
    token = issue_session(user, config, now=100)
    assert read_session(token, config, now=101) == user
    assert read_session(f"{token[:-1]}x", config, now=101) is None
    assert read_session(token, config, now=100 + config.session_ttl_seconds) is None


def test_login_cookie_protects_product_api_and_logout_revokes_browser_session(monkeypatch):
    configure_auth(monkeypatch)
    app = create_app()

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://localhost"
        ) as client:
            assert (await client.get("/health")).status_code == 200
            assert (await client.get("/api/v1/territories")).status_code == 401
            rejected = await client.post(
                "/api/v1/auth/login",
                json={"username": "dispatcher", "password": "wrong"},
            )
            assert rejected.status_code == 401
            accepted = await client.post(
                "/api/v1/auth/login",
                json={"username": "dispatcher", "password": "test-password"},
            )
            assert accepted.status_code == 200
            assert accepted.json() == {
                "username": "dispatcher",
                "display_name": "Диспетчер смены",
                "role": "dispatcher",
            }
            cookie = accepted.headers["set-cookie"]
            assert "HttpOnly" in cookie and "SameSite=lax" in cookie
            assert (await client.get("/api/v1/auth/me")).status_code == 200
            assert (await client.get("/api/v1/territories")).status_code == 200
            assert (await client.post("/api/v1/auth/logout")).status_code == 204
            assert (await client.get("/api/v1/territories")).status_code == 401

    asyncio.run(run())

"""API service smoke tests — the FastAPI app must build and serve the routes
the Next.js frontend's /api/adk proxy allowlist depends on."""

import pytest


@pytest.fixture(scope="module")
def api_app():
    from api.main import app

    return app


def test_frontend_contract_routes_exist(api_app):
    paths = {getattr(r, "path", "") for r in api_app.routes}
    required = {
        "/apps/{app_name}/users/{user_id}/sessions",
        "/apps/{app_name}/users/{user_id}/sessions/{session_id}",
        "/apps/{app_name}/users/{user_id}/sessions/{session_id}/artifacts",
        "/apps/{app_name}/users/{user_id}/sessions/{session_id}/artifacts/{artifact_name:path}",
        "/run_sse",
        "/list-apps",
    }
    missing = required - paths
    assert not missing, f"Frontend-required routes missing from API app: {missing}"


@pytest.mark.asyncio
async def test_health_and_root(api_app):
    import httpx

    transport = httpx.ASGITransport(app=api_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        health = await client.get("/healthz")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        root = await client.get("/")
        assert root.status_code == 200
        assert root.json()["service"] == "agent-guardian-api"


@pytest.mark.asyncio
async def test_list_apps_includes_agent_guardian(api_app):
    import httpx

    transport = httpx.ASGITransport(app=api_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/list-apps")
        assert resp.status_code == 200
        assert "agent_guardian" in resp.json()

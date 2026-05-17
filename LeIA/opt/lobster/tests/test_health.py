import httpx

from lobster_agent.config import Settings
from lobster_agent.main import create_app


async def test_health_returns_200(settings: Settings) -> None:
    app = create_app(settings)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        r = await client.get("/health")

    assert r.status_code == 200


async def test_health_schema(settings: Settings) -> None:
    app = create_app(settings)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        data = (await client.get("/health")).json()

    assert data["status"] == "ok"
    assert data["version"] == "0.1.0"
    assert isinstance(data["uptime_seconds"], float)


async def test_metrics_returns_prometheus(settings: Settings) -> None:
    app = create_app(settings)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        r = await client.get("/metrics")

    assert r.status_code == 200
    assert "lobster_info" in r.text
    assert "lobster_uptime_seconds" in r.text

import httpx

from lobster_agent.config import Settings
from lobster_agent.main import create_app


async def test_webhook_alert_returns_202(settings: Settings) -> None:
    app = create_app(settings)
    payload = {
        "version": "4",
        "status": "firing",
        "groupKey": "{}:{alertname='TestAlert'}",
        "groupLabels": {"alertname": "TestAlert"},
        "commonLabels": {"alertname": "TestAlert", "severity": "warning"},
        "commonAnnotations": {"summary": "Test alert firing"},
        "alerts": [
            {
                "status": "firing",
                "labels": {"alertname": "TestAlert"},
                "annotations": {"summary": "Test"},
                "startsAt": "2024-01-01T00:00:00Z",
                "endsAt": "0001-01-01T00:00:00Z",
                "generatorURL": "",
            }
        ],
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        r = await client.post("/webhook/alert", json=payload)

    assert r.status_code == 202
    assert r.json()["status"] == "accepted"


async def test_webhook_alert_400_on_invalid_json(settings: Settings) -> None:
    app = create_app(settings)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        r = await client.post(
            "/webhook/alert",
            content=b"not json {{{",
            headers={"Content-Type": "application/json"},
        )

    assert r.status_code == 400


async def test_webhook_alert_resolved_status(settings: Settings) -> None:
    app = create_app(settings)
    payload = {
        "version": "4",
        "status": "resolved",
        "groupLabels": {},
        "commonLabels": {},
        "commonAnnotations": {},
        "alerts": [],
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        r = await client.post("/webhook/alert", json=payload)

    assert r.status_code == 202


async def test_webhook_alert_accepts_minimal_payload(settings: Settings) -> None:
    app = create_app(settings)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        r = await client.post("/webhook/alert", json={})

    assert r.status_code == 202


async def test_webhook_drops_lobster_self_alert_by_common_labels(
    settings: Settings,
) -> None:
    app = create_app(settings)
    payload = {
        "status": "firing",
        "commonLabels": {"alertname": "LobsterRestart", "team": "ops"},
        "commonAnnotations": {"summary": "Lobster se ha reiniciado"},
        "alerts": [
            {
                "status": "firing",
                "labels": {"alertname": "LobsterRestart", "team": "ops"},
                "annotations": {},
            }
        ],
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        r = await client.post("/webhook/alert", json=payload)

    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "accepted"
    assert body.get("dropped") == "self_alert"


async def test_webhook_drops_lobster_self_alert_when_only_per_alert_labels(
    settings: Settings,
) -> None:
    app = create_app(settings)
    payload = {
        "status": "firing",
        "commonLabels": {},
        "alerts": [
            {
                "status": "firing",
                "labels": {"alertname": "LobsterSinActividad"},
                "annotations": {},
            }
        ],
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        r = await client.post("/webhook/alert", json=payload)

    assert r.status_code == 202
    assert r.json().get("dropped") == "self_alert"


async def test_webhook_does_not_drop_unrelated_alert(settings: Settings) -> None:
    app = create_app(settings)
    payload = {
        "status": "firing",
        "commonLabels": {"alertname": "TenantPodCrashLoop"},
        "alerts": [
            {
                "status": "firing",
                "labels": {"alertname": "TenantPodCrashLoop", "namespace": "tenant-foo"},
                "annotations": {},
            }
        ],
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        r = await client.post("/webhook/alert", json=payload)

    assert r.status_code == 202
    assert "dropped" not in r.json()

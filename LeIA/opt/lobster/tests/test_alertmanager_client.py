from datetime import UTC, datetime

import httpx
import pytest
import respx

from lobster_agent.clients.alertmanager import (
    AlertmanagerClient,
    AlertmanagerHTTPError,
    AlertmanagerTimeoutError,
)


def _alert_payload(fingerprint: str, ends_at: str | None = None) -> dict[str, object]:
    return {
        "fingerprint": fingerprint,
        "status": {"state": "active"},
        "labels": {
            "alertname": "HighCPU",
            "severity": "critical",
            "instance": "matrix",
        },
        "annotations": {"summary": "CPU high"},
        "startsAt": "2026-05-11T10:00:00Z",
        "endsAt": ends_at,
        "generatorURL": "http://prometheus.test/graph",
    }


@pytest.mark.respx(base_url="http://alertmanager.test")
async def test_list_active_alerts_returns_alerts(respx_mock: respx.Router) -> None:
    respx_mock.get("/api/v2/alerts").mock(
        return_value=httpx.Response(
            200,
            json=[
                _alert_payload("abc", None),
                _alert_payload("def", "2026-05-11T10:15:00Z"),
            ],
        )
    )
    client = AlertmanagerClient("http://alertmanager.test")

    result = await client.list_active_alerts({"severity": "critical"})

    assert len(result) == 2
    assert result[0].fingerprint == "abc"
    assert result[0].ends_at is None
    assert result[0].severity == "critical"
    assert result[1].ends_at == datetime(2026, 5, 11, 10, 15, tzinfo=UTC)
    await client.close()


@pytest.mark.respx(base_url="http://alertmanager.test")
async def test_get_alert_by_fingerprint_returns_match(respx_mock: respx.Router) -> None:
    respx_mock.get("/api/v2/alerts").mock(
        return_value=httpx.Response(200, json=[_alert_payload("abc"), _alert_payload("def")])
    )
    client = AlertmanagerClient("http://alertmanager.test")

    result = await client.get_alert_by_fingerprint("def")

    assert result is not None
    assert result.fingerprint == "def"
    await client.close()


@pytest.mark.respx(base_url="http://alertmanager.test")
async def test_get_alert_by_fingerprint_returns_none(respx_mock: respx.Router) -> None:
    respx_mock.get("/api/v2/alerts").mock(
        return_value=httpx.Response(200, json=[_alert_payload("abc")])
    )
    client = AlertmanagerClient("http://alertmanager.test")

    assert await client.get_alert_by_fingerprint("missing") is None
    await client.close()


@pytest.mark.respx(base_url="http://alertmanager.test")
async def test_timeout_raises_typed_error(respx_mock: respx.Router) -> None:
    respx_mock.get("/api/v2/alerts").mock(side_effect=httpx.ReadTimeout("slow"))
    client = AlertmanagerClient("http://alertmanager.test")

    with pytest.raises(AlertmanagerTimeoutError):
        await client.list_active_alerts()

    await client.close()


@pytest.mark.respx(base_url="http://alertmanager.test")
async def test_http_500_raises_typed_error(respx_mock: respx.Router) -> None:
    respx_mock.get("/api/v2/alerts").mock(return_value=httpx.Response(500, text="boom"))
    client = AlertmanagerClient("http://alertmanager.test")

    with pytest.raises(AlertmanagerHTTPError) as exc_info:
        await client.list_active_alerts()

    assert exc_info.value.status_code == 500
    await client.close()


@pytest.mark.respx(base_url="http://alertmanager.test")
async def test_list_silences_returns_active_only(respx_mock: respx.Router) -> None:
    respx_mock.get("/api/v2/silences").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "silence-a",
                    "matchers": [{"name": "severity", "value": "warning", "isRegex": False}],
                    "startsAt": "2026-05-11T09:00:00Z",
                    "endsAt": "2026-05-11T11:00:00Z",
                    "createdBy": "lobster",
                    "comment": "maintenance",
                    "status": {"state": "active"},
                },
                {
                    "id": "silence-b",
                    "matchers": [],
                    "startsAt": "2026-05-11T09:00:00Z",
                    "endsAt": "2026-05-11T09:30:00Z",
                    "createdBy": "lobster",
                    "comment": "expired",
                    "status": {"state": "expired"},
                },
            ],
        )
    )
    client = AlertmanagerClient("http://alertmanager.test")

    result = await client.list_silences()

    assert len(result) == 1
    assert result[0].id == "silence-a"
    assert result[0].status == {"state": "active"}
    await client.close()


@pytest.mark.respx(base_url="http://alertmanager.test")
async def test_get_status_returns_version_and_uptime(respx_mock: respx.Router) -> None:
    respx_mock.get("/api/v2/status").mock(
        return_value=httpx.Response(
            200,
            json={
                "cluster": {"status": "ready"},
                "versionInfo": {"version": "0.27.0"},
                "uptime": "2026-05-11T08:00:00Z",
            },
        )
    )
    client = AlertmanagerClient("http://alertmanager.test")

    result = await client.get_status()

    assert result.cluster_status == "ready"
    assert result.version == "0.27.0"
    assert result.uptime == datetime(2026, 5, 11, 8, tzinfo=UTC)
    await client.close()

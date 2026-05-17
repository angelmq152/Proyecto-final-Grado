from datetime import UTC, datetime

import httpx
import pytest
import respx

from lobster_agent.clients.prometheus import PrometheusClient, PrometheusQueryError


@pytest.mark.respx(base_url="http://prometheus.test")
async def test_instant_query_returns_result(respx_mock: respx.Router) -> None:
    respx_mock.get("/api/v1/query").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "success",
                "data": {"result": [{"metric": {"job": "node"}, "value": [1, "1"]}]},
            },
        )
    )
    client = PrometheusClient("http://prometheus.test")

    result = await client.instant_query("up")

    assert result == [{"metric": {"job": "node"}, "value": [1, "1"]}]
    await client.close()


@pytest.mark.respx(base_url="http://prometheus.test")
async def test_range_query_returns_result(respx_mock: respx.Router) -> None:
    respx_mock.get("/api/v1/query_range").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "success",
                "data": {"result": [{"metric": {"job": "api"}, "values": [[1, "2"]]}]},
            },
        )
    )
    client = PrometheusClient("http://prometheus.test")

    result = await client.range_query(
        "rate(http_requests_total[5m])",
        datetime(2026, 5, 10, tzinfo=UTC),
        datetime(2026, 5, 10, 0, 5, tzinfo=UTC),
        "30s",
    )

    assert result == [{"metric": {"job": "api"}, "values": [[1, "2"]]}]
    await client.close()


@pytest.mark.respx(base_url="http://prometheus.test")
async def test_list_labels_returns_data(respx_mock: respx.Router) -> None:
    respx_mock.get("/api/v1/labels").mock(
        return_value=httpx.Response(200, json={"status": "success", "data": ["job", "instance"]})
    )
    client = PrometheusClient("http://prometheus.test")

    assert await client.list_labels() == ["job", "instance"]
    await client.close()


@pytest.mark.respx(base_url="http://prometheus.test")
async def test_list_series_returns_data(respx_mock: respx.Router) -> None:
    respx_mock.get("/api/v1/series").mock(
        return_value=httpx.Response(
            200,
            json={"status": "success", "data": [{"__name__": "up", "job": "node"}]},
        )
    )
    client = PrometheusClient("http://prometheus.test")

    assert await client.list_series("up") == [{"__name__": "up", "job": "node"}]
    await client.close()


@pytest.mark.respx(base_url="http://prometheus.test")
async def test_status_error_raises_query_error(respx_mock: respx.Router) -> None:
    respx_mock.get("/api/v1/query").mock(
        return_value=httpx.Response(
            200,
            json={"status": "error", "errorType": "bad_data", "error": "invalid query"},
        )
    )
    client = PrometheusClient("http://prometheus.test")

    with pytest.raises(PrometheusQueryError):
        await client.instant_query("bad")

    await client.close()


@pytest.mark.respx(base_url="http://prometheus.test")
async def test_http_500_raises_query_error(respx_mock: respx.Router) -> None:
    respx_mock.get("/api/v1/query").mock(return_value=httpx.Response(500, text="boom"))
    client = PrometheusClient("http://prometheus.test")

    with pytest.raises(PrometheusQueryError):
        await client.instant_query("up")

    await client.close()

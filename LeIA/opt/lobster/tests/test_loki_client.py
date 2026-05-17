from datetime import UTC, datetime

import httpx
import pytest
import respx

from lobster_agent.clients.loki import LokiClient, LokiQueryError


@pytest.mark.respx(base_url="http://loki.test")
async def test_query_range_returns_log_entries(respx_mock: respx.Router) -> None:
    timestamp_ns = "1778400000123456789"
    respx_mock.get("/loki/api/v1/query_range").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "success",
                "data": {
                    "result": [
                        {
                            "stream": {"service": "lobster", "level": "info"},
                            "values": [[timestamp_ns, "hello"]],
                        }
                    ]
                },
            },
        )
    )
    client = LokiClient("http://loki.test")

    result = await client.query_range(
        '{service="lobster"}',
        datetime(2026, 5, 10, tzinfo=UTC),
        datetime(2026, 5, 10, 0, 5, tzinfo=UTC),
    )

    assert len(result) == 1
    assert result[0].labels == {"service": "lobster", "level": "info"}
    assert result[0].line == "hello"
    await client.close()


@pytest.mark.respx(base_url="http://loki.test")
async def test_query_range_converts_nanosecond_timestamp_to_utc(
    respx_mock: respx.Router,
) -> None:
    timestamp_ns = "1778400000123456789"
    respx_mock.get("/loki/api/v1/query_range").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "success",
                "data": {"result": [{"stream": {}, "values": [[timestamp_ns, "line"]]}]},
            },
        )
    )
    client = LokiClient("http://loki.test")

    result = await client.query_range(
        '{job="test"}',
        datetime(2026, 5, 10, tzinfo=UTC),
        datetime(2026, 5, 10, 0, 1, tzinfo=UTC),
    )

    assert result[0].timestamp.tzinfo == UTC
    assert result[0].timestamp == datetime.fromtimestamp(1778400000.123456789, UTC)
    await client.close()


@pytest.mark.respx(base_url="http://loki.test")
async def test_list_labels_returns_data(respx_mock: respx.Router) -> None:
    respx_mock.get("/loki/api/v1/labels").mock(
        return_value=httpx.Response(200, json={"status": "success", "data": ["service", "level"]})
    )
    client = LokiClient("http://loki.test")

    assert await client.list_labels() == ["service", "level"]
    await client.close()


@pytest.mark.respx(base_url="http://loki.test")
async def test_list_series_returns_data(respx_mock: respx.Router) -> None:
    respx_mock.get("/loki/api/v1/series").mock(
        return_value=httpx.Response(
            200,
            json={"status": "success", "data": [{"service": "lobster"}]},
        )
    )
    client = LokiClient("http://loki.test")

    assert await client.list_series('{service="lobster"}') == [{"service": "lobster"}]
    await client.close()


@pytest.mark.respx(base_url="http://loki.test")
async def test_status_error_raises_query_error(respx_mock: respx.Router) -> None:
    respx_mock.get("/loki/api/v1/query_range").mock(
        return_value=httpx.Response(
            200,
            json={"status": "error", "errorType": "bad_data", "error": "invalid logql"},
        )
    )
    client = LokiClient("http://loki.test")

    with pytest.raises(LokiQueryError):
        await client.query_range(
            "bad",
            datetime(2026, 5, 10, tzinfo=UTC),
            datetime(2026, 5, 10, 0, 1, tzinfo=UTC),
        )

    await client.close()


@pytest.mark.respx(base_url="http://loki.test")
async def test_http_500_raises_query_error(respx_mock: respx.Router) -> None:
    respx_mock.get("/loki/api/v1/query_range").mock(return_value=httpx.Response(500, text="boom"))
    client = LokiClient("http://loki.test")

    with pytest.raises(LokiQueryError):
        await client.query_range(
            '{service="lobster"}',
            datetime(2026, 5, 10, tzinfo=UTC),
            datetime(2026, 5, 10, 0, 1, tzinfo=UTC),
        )

    await client.close()

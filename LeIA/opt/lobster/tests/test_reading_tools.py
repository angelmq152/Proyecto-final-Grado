from datetime import UTC, datetime

from lobster_agent.agent.tools.reading import (
    get_global_health,
    get_node_metrics,
    get_tenant_metrics,
    query_loki,
    query_prometheus,
)
from lobster_agent.clients.loki import LogEntry


class FakePrometheusClient:
    def __init__(self, results_by_query: dict[str, list[dict[str, object]]] | None = None) -> None:
        self.results_by_query = results_by_query or {}
        self.queries: list[str] = []

    async def instant_query(self, query: str) -> list[dict[str, object]]:
        self.queries.append(query)
        return self.results_by_query.get(query, [])


class FakeLokiClient:
    def __init__(self, entries: list[LogEntry]) -> None:
        self.entries = entries
        self.calls: list[tuple[str, datetime, datetime, int]] = []

    async def query_range(
        self,
        logql: str,
        start: datetime,
        end: datetime,
        limit: int = 100,
    ) -> list[LogEntry]:
        self.calls.append((logql, start, end, limit))
        return self.entries


async def test_query_prometheus_calls_instant_query() -> None:
    client = FakePrometheusClient({"up": [{"metric": {"job": "node"}, "value": [1, "1"]}]})

    result = await query_prometheus(client, "up")

    assert client.queries == ["up"]
    assert result == [{"metric": {"job": "node"}, "value": [1, "1"]}]


async def test_query_loki_converts_entries_to_public_model() -> None:
    start = datetime(2026, 5, 11, 10, 0, tzinfo=UTC)
    end = datetime(2026, 5, 11, 10, 5, tzinfo=UTC)
    client = FakeLokiClient(
        [
            LogEntry(
                timestamp=start,
                labels={"service": "lobster"},
                line="hello",
            )
        ]
    )

    result = await query_loki(client, '{service="lobster"}', start, end, limit=10)

    assert client.calls == [('{service="lobster"}', start, end, 10)]
    assert result[0].timestamp == start
    assert result[0].labels == {"service": "lobster"}
    assert result[0].line == "hello"


async def test_get_node_metrics_parses_prometheus_values() -> None:
    client = FakePrometheusClient()

    async def instant_query(query: str) -> list[dict[str, object]]:
        client.queries.append(query)
        if query.startswith("100 - avg"):
            return [{"value": [1, "23.5"]}]
        return [{"value": [1, "61.25"]}]

    client.instant_query = instant_query

    result = await get_node_metrics(client, "matrix:9100")

    assert result.node == "matrix:9100"
    assert result.cpu_pct == 23.5
    assert result.memory_pct == 61.25


async def test_get_node_metrics_tolerates_empty_results() -> None:
    client = FakePrometheusClient()

    result = await get_node_metrics(client, "matrix:9100")

    assert result.cpu_pct == 0.0
    assert result.memory_pct == 0.0


async def test_get_global_health_returns_utc_timestamp() -> None:
    client = FakePrometheusClient(
        {
            "up": [
                {"metric": {"instance": "matrix:9100"}, "value": [1, "1"]},
                {"metric": {"instance": "sauron:9100"}, "value": [1, "1"]},
            ]
        }
    )

    result = await get_global_health(client)

    assert result.timestamp.tzinfo == UTC
    assert [node.node for node in result.nodes] == ["matrix:9100", "sauron:9100"]
    assert result.total_tenants is None
    assert result.tenants_active is None


async def test_get_tenant_metrics_returns_namespace() -> None:
    client = FakePrometheusClient()

    result = await get_tenant_metrics(client, "tenant-a")

    assert result.namespace == "tenant-a"
    assert result.cpu_avg is None

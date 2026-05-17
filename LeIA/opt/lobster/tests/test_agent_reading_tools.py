from datetime import datetime
from types import SimpleNamespace

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lobster_agent.agent.deps import AgentDeps
from lobster_agent.agent.orchestrator import LobsterAgent
from lobster_agent.agent.routing import CaseUse
from lobster_agent.agent.tools import reading
from lobster_agent.clients.alertmanager import AlertmanagerAlert
from lobster_agent.clients.loki import LogEntry
from lobster_agent.clients.prometheus import PrometheusTimeoutError
from lobster_agent.persistence.db import create_db_engine, create_db_schema, create_sessionmaker
from lobster_agent.persistence.repositories import DecisionRepository
from tests.conftest import make_test_settings


class FakePrometheusClient:
    def __init__(self) -> None:
        self.instant_queries: list[str] = []

    async def instant_query(self, query: str) -> list[dict[str, object]]:
        self.instant_queries.append(query)
        return [{"metric": {"job": "node"}, "value": [1, "1"]}]

    async def range_query(
        self,
        query: str,
        start: datetime,
        end: datetime,
        step: str,
    ) -> list[dict[str, object]]:
        return [{"metric": {"job": "node"}, "values": [[1, "1"]]}]


class TimeoutPrometheusClient(FakePrometheusClient):
    async def instant_query(self, query: str) -> list[dict[str, object]]:
        raise PrometheusTimeoutError("timeout")


class FakeLokiClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    async def query_range(
        self,
        logql: str,
        start: datetime,
        end: datetime,
        limit: int = 100,
    ) -> list[LogEntry]:
        self.calls.append((logql, limit))
        return [LogEntry(timestamp=end, labels={"service": "lobster"}, line="error line")]


class FakeK8sClient:
    async def list_namespaces(self, label_selector: str | None = None) -> list[object]:
        return [SimpleNamespace(metadata=SimpleNamespace(name="default"))]

    async def list_pods(self, namespace: str) -> list[object]:
        return []

    async def get_pod(self, namespace: str, name: str) -> object:
        raise RuntimeError(name)

    async def list_deployments(self, namespace: str) -> list[object]:
        return []

    async def list_events(self, namespace: str) -> list[object]:
        return []


class FakeAlertmanagerClient:
    def __init__(self) -> None:
        self.severities: list[str | None] = []

    async def list_active_alerts(
        self,
        label_filters: dict[str, str] | None = None,
    ) -> list[AlertmanagerAlert]:
        self.severities.append(None if label_filters is None else label_filters.get("severity"))
        return [
            AlertmanagerAlert.model_validate(
                {
                    "fingerprint": "abc",
                    "status": "active",
                    "labels": {"alertname": "HighCPU", "severity": "critical"},
                    "annotations": {"summary": "CPU high"},
                    "startsAt": "2026-05-11T10:00:00Z",
                    "endsAt": None,
                    "generatorURL": None,
                }
            )
        ]

    async def get_alert_by_fingerprint(self, fingerprint: str) -> AlertmanagerAlert | None:
        return None


def _model_calling(tool_calls: list[ToolCallPart]) -> FunctionModel:
    async def function(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        _ = info
        if any(isinstance(part, ToolReturnPart) for message in messages for part in message.parts):
            returned = [
                part
                for message in messages
                for part in message.parts
                if isinstance(part, ToolReturnPart)
            ]
            return ModelResponse(parts=[TextPart(content=str([part.content for part in returned]))])
        return ModelResponse(parts=tool_calls)

    return FunctionModel(function)


async def _deps(
    session_maker: async_sessionmaker[AsyncSession],
    prometheus: object | None = None,
    loki: object | None = None,
    alertmanager: object | None = None,
) -> AgentDeps:
    return AgentDeps(
        prometheus=prometheus or FakePrometheusClient(),
        loki=loki or FakeLokiClient(),
        k8s=FakeK8sClient(),
        alertmanager=alertmanager or FakeAlertmanagerClient(),
        decisions_repo=DecisionRepository(session_maker),
    )


async def test_health_loop_read_invokes_prometheus_and_alertmanager(tmp_path) -> None:
    db_path = tmp_path / "state.db"
    settings = make_test_settings(database={"url": f"sqlite+aiosqlite:///{db_path}"})
    engine = create_db_engine(settings.database.url)
    await create_db_schema(engine)
    session_maker = create_sessionmaker(engine)
    prometheus = FakePrometheusClient()
    alertmanager = FakeAlertmanagerClient()

    deps = await _deps(session_maker, prometheus=prometheus, alertmanager=alertmanager)
    model = _model_calling(
        [
            ToolCallPart(
                tool_name="query_prometheus_instant",
                args={"query": "up"},
                tool_call_id="prom",
            ),
            ToolCallPart(
                tool_name="list_active_alerts",
                args={"severity": "critical"},
                tool_call_id="alerts",
            ),
        ]
    )
    agent = LobsterAgent(settings, deps=deps, model_factory=lambda _m, _t: model)
    result = await agent.run(CaseUse.HEALTH_LOOP_READ, "health")
    await agent.close()

    assert result.outcome == "success"
    assert prometheus.instant_queries == ["up"]
    assert alertmanager.severities == ["critical"]
    await engine.dispose()


async def test_diagnose_can_invoke_loki_logs() -> None:
    loki = FakeLokiClient()
    agent = Agent(
        _model_calling(
            [
                ToolCallPart(
                    tool_name="query_loki_logs",
                    args={"logql": '{service="lobster"}', "minutes": 5},
                    tool_call_id="loki",
                )
            ]
        ),
        deps_type=AgentDeps,
        tools=[reading.query_loki_logs],
    )
    deps = AgentDeps(
        prometheus=FakePrometheusClient(),
        loki=loki,
        k8s=FakeK8sClient(),
        alertmanager=FakeAlertmanagerClient(),
        decisions_repo=DecisionRepository(SimpleNamespace()),
    )

    result = await agent.run("diagnose", deps=deps)

    assert result.output
    assert loki.calls == [('{service="lobster"}', 100)]


async def test_prometheus_range_rejects_invalid_minutes() -> None:
    agent = Agent(
        _model_calling(
            [
                ToolCallPart(
                    tool_name="query_prometheus_range",
                    args={"query": "up", "minutes": 10000},
                    tool_call_id="range",
                )
            ]
        ),
        deps_type=AgentDeps,
        tools=[reading.query_prometheus_range],
        tool_retries=0,
    )
    deps = AgentDeps(
        prometheus=FakePrometheusClient(),
        loki=FakeLokiClient(),
        k8s=FakeK8sClient(),
        alertmanager=FakeAlertmanagerClient(),
        decisions_repo=DecisionRepository(SimpleNamespace()),
    )

    with pytest.raises(Exception):
        await agent.run("bad range", deps=deps)


async def test_prometheus_timeout_returns_tool_error() -> None:
    agent = Agent(
        _model_calling(
            [
                ToolCallPart(
                    tool_name="query_prometheus_instant",
                    args={"query": "up"},
                    tool_call_id="prom",
                )
            ]
        ),
        deps_type=AgentDeps,
        tools=[reading.query_prometheus_instant],
    )
    deps = AgentDeps(
        prometheus=TimeoutPrometheusClient(),
        loki=FakeLokiClient(),
        k8s=FakeK8sClient(),
        alertmanager=FakeAlertmanagerClient(),
        decisions_repo=DecisionRepository(SimpleNamespace()),
    )

    result = await agent.run("timeout", deps=deps)

    assert "ToolError" in result.output
    assert "prometheus" in result.output


async def test_agent_persists_tools_called(tmp_path) -> None:
    db_path = tmp_path / "state.db"
    settings = make_test_settings(database={"url": f"sqlite+aiosqlite:///{db_path}"})
    engine = create_db_engine(settings.database.url)
    await create_db_schema(engine)
    session_maker = create_sessionmaker(engine)

    deps = await _deps(session_maker)
    model = _model_calling(
        [
            ToolCallPart(
                tool_name="list_active_alerts",
                args={},
                tool_call_id="alerts",
            )
        ]
    )
    agent = LobsterAgent(settings, deps=deps, model_factory=lambda _m, _t: model)
    result = await agent.run(CaseUse.SUMMARY, "summary")
    await agent.close()

    repo = DecisionRepository(session_maker)
    decision = await repo.get_by_id(result.decision_id)

    assert decision is not None
    assert decision.tools_called == ["list_active_alerts"]
    await engine.dispose()

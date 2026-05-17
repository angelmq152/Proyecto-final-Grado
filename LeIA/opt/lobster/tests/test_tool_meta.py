from types import SimpleNamespace
from unittest.mock import AsyncMock

from lobster_agent.agent.tools.meta import request_new_tool
from lobster_agent.persistence.db import create_db_engine, create_db_schema, create_sessionmaker
from lobster_agent.persistence.repositories import ToolRequestRepository
from lobster_agent.telegram.notifier import FakeTelegramNotifier
from tests.conftest import make_test_settings


async def _setup(tmp_path):
    engine = create_db_engine(f"sqlite+aiosqlite:///{tmp_path / 'state.db'}")
    await create_db_schema(engine)
    session_maker = create_sessionmaker(engine)
    repo = ToolRequestRepository(session_maker)
    return repo, engine


def _make_ctx(repo, notifier, case_use="chat"):
    from lobster_agent.agent.deps import AgentDeps
    from lobster_agent.clients.alertmanager import AlertmanagerClient
    from lobster_agent.clients.k8s import K8sClient
    from lobster_agent.clients.loki import LokiClient
    from lobster_agent.clients.prometheus import PrometheusClient
    from lobster_agent.persistence.repositories import DecisionRepository

    async def repo_factory() -> ToolRequestRepository:
        return repo

    deps = AgentDeps(
        prometheus=AsyncMock(spec=PrometheusClient),
        loki=AsyncMock(spec=LokiClient),
        k8s=AsyncMock(spec=K8sClient),
        alertmanager=AsyncMock(spec=AlertmanagerClient),
        decisions_repo=AsyncMock(spec=DecisionRepository),
        tool_request_repo_factory=repo_factory,
        notifier=notifier,
        current_case_use=case_use,
    )
    return SimpleNamespace(deps=deps)


async def test_creates_tool_request_row(tmp_path) -> None:
    settings = make_test_settings(telegram={"allowed_user_ids": [111]})
    repo, engine = await _setup(tmp_path)
    notifier = FakeTelegramNotifier(settings)
    ctx = _make_ctx(repo, notifier)

    await request_new_tool(
        ctx, "kubectl_exec", "Execute a command in a pod", ["pod_name", "command"]
    )

    rows = await repo.list_recent()
    assert len(rows) == 1
    assert rows[0].tool_name_suggested == "kubectl_exec"
    assert rows[0].description == "Execute a command in a pod"
    assert rows[0].status == "pending"
    assert rows[0].case_use == "chat"

    await engine.dispose()


async def test_calls_notifier_send_to_admin(tmp_path) -> None:
    settings = make_test_settings(telegram={"allowed_user_ids": [111]})
    repo, engine = await _setup(tmp_path)
    notifier = FakeTelegramNotifier(settings)
    ctx = _make_ctx(repo, notifier)

    await request_new_tool(ctx, "scale_deployment", "Scale a deployment", [])

    assert any(
        method == "send_to_admin" and "scale_deployment" in str(arg)
        for method, arg in notifier.calls
    )

    await engine.dispose()


async def test_returns_confirmation_string(tmp_path) -> None:
    settings = make_test_settings(telegram={"allowed_user_ids": [111]})
    repo, engine = await _setup(tmp_path)
    notifier = FakeTelegramNotifier(settings)
    ctx = _make_ctx(repo, notifier)

    result = await request_new_tool(ctx, "some_tool", "desc", [])

    assert "Solicitud registrada" in result
    assert "operador" in result

    await engine.dispose()


async def test_duplicate_names_create_two_rows(tmp_path) -> None:
    settings = make_test_settings(telegram={"allowed_user_ids": [111]})
    repo, engine = await _setup(tmp_path)
    notifier = FakeTelegramNotifier(settings)
    ctx = _make_ctx(repo, notifier)

    await request_new_tool(ctx, "same_tool", "first request", [])
    await request_new_tool(ctx, "same_tool", "second request", [])

    rows = await repo.list_recent()
    assert len(rows) == 2

    await engine.dispose()


async def test_returns_unavailable_when_factory_missing(tmp_path) -> None:
    from lobster_agent.agent.deps import AgentDeps
    from lobster_agent.clients.alertmanager import AlertmanagerClient
    from lobster_agent.clients.k8s import K8sClient
    from lobster_agent.clients.loki import LokiClient
    from lobster_agent.clients.prometheus import PrometheusClient
    from lobster_agent.persistence.repositories import DecisionRepository

    deps = AgentDeps(
        prometheus=AsyncMock(spec=PrometheusClient),
        loki=AsyncMock(spec=LokiClient),
        k8s=AsyncMock(spec=K8sClient),
        alertmanager=AsyncMock(spec=AlertmanagerClient),
        decisions_repo=AsyncMock(spec=DecisionRepository),
    )
    ctx = SimpleNamespace(deps=deps)
    result = await request_new_tool(ctx, "some_tool", "desc", [])
    assert "not available" in result

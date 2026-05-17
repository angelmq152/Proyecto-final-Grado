from types import SimpleNamespace
from typing import Any, cast

import pytest
from pydantic_ai import RunContext

from lobster_agent.agent.deps import AgentDeps
from lobster_agent.agent.tools.reading import NodeAliveness, ToolError, is_node_alive
from lobster_agent.clients.k8s import K8sClient, K8sClientError


class FakeK8sClient:
    def __init__(self, *, ready: bool | None = True, raise_error: bool = False) -> None:
        self._ready = ready
        self._raise = raise_error
        self.calls: list[str] = []

    async def get_node_ready(self, name: str) -> bool:
        self.calls.append(name)
        if self._raise:
            raise K8sClientError(f"node {name} not found")
        assert self._ready is not None
        return self._ready


def _make_ctx(k8s: Any) -> RunContext[AgentDeps]:
    deps = SimpleNamespace(k8s=k8s)
    return cast(RunContext[AgentDeps], SimpleNamespace(deps=deps))


async def test_is_node_alive_returns_true_when_node_ready() -> None:
    k8s = FakeK8sClient(ready=True)
    ctx = _make_ctx(k8s)

    result = await is_node_alive(ctx, "matrix")

    assert isinstance(result, NodeAliveness)
    assert result.node == "matrix"
    assert result.alive is True
    assert k8s.calls == ["matrix"]


async def test_is_node_alive_returns_false_when_node_not_ready() -> None:
    k8s = FakeK8sClient(ready=False)
    ctx = _make_ctx(k8s)

    result = await is_node_alive(ctx, "matrix")

    assert isinstance(result, NodeAliveness)
    assert result.alive is False
    assert "not Ready" in result.detail


async def test_is_node_alive_returns_tool_error_on_k8s_failure() -> None:
    k8s = FakeK8sClient(raise_error=True)
    ctx = _make_ctx(k8s)

    result = await is_node_alive(ctx, "fallback")

    assert isinstance(result, ToolError)
    assert result.source == "k8s"
    assert "not found" in result.message


# ---------------------------------------------------------------------------
# Low-level test for K8sClient.get_node_ready: parsing of node.status.conditions
# ---------------------------------------------------------------------------


def _node_with_conditions(conditions: list[dict[str, str]]) -> object:
    return SimpleNamespace(
        metadata=SimpleNamespace(name="matrix"),
        status=SimpleNamespace(conditions=[SimpleNamespace(**c) for c in conditions]),
    )


class _GetPatch:
    def __init__(self, node: object | Exception) -> None:
        self._node = node

    async def __call__(self, resource: Any, name: str, namespace: str | None = None) -> object:
        if isinstance(self._node, Exception):
            raise self._node
        return self._node


@pytest.fixture
def client() -> K8sClient:
    return K8sClient(kubeconfig_path="/dev/null")


async def test_get_node_ready_true_when_ready_condition_true(
    client: K8sClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    node = _node_with_conditions(
        [
            {"type": "MemoryPressure", "status": "False"},
            {"type": "Ready", "status": "True"},
        ]
    )
    monkeypatch.setattr(client, "_get", _GetPatch(node))

    assert await client.get_node_ready("matrix") is True


async def test_get_node_ready_false_when_ready_condition_false(
    client: K8sClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    node = _node_with_conditions(
        [
            {"type": "Ready", "status": "False"},
        ]
    )
    monkeypatch.setattr(client, "_get", _GetPatch(node))

    assert await client.get_node_ready("matrix") is False


async def test_get_node_ready_false_when_no_ready_condition(
    client: K8sClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    node = _node_with_conditions(
        [
            {"type": "DiskPressure", "status": "False"},
        ]
    )
    monkeypatch.setattr(client, "_get", _GetPatch(node))

    assert await client.get_node_ready("matrix") is False


async def test_get_node_ready_raises_when_node_missing(
    client: K8sClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(client, "_get", _GetPatch(RuntimeError("404")))

    with pytest.raises(K8sClientError, match="Failed to read node"):
        await client.get_node_ready("ghost")

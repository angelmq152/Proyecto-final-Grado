from typing import Any

import pytest
from pydantic_ai import RunContext

from lobster_agent.agent.deps import AgentDeps
from lobster_agent.agent.mutations.context import ActionResult
from lobster_agent.agent.tools.mutations.node import (
    pin_deployment_to_node,
    unpin_deployment_from_node,
)
from lobster_agent.clients.k8s import K8sClientError
from lobster_agent.domain.severity import ActionSeverity
from lobster_agent.persistence.models import ActionStatus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _deployment(replicas: int = 1, node_selector: dict[str, str] | None = None) -> dict[str, Any]:
    pod_spec: dict[str, Any] = {}
    if node_selector is not None:
        pod_spec["nodeSelector"] = node_selector
    return {
        "spec": {
            "replicas": replicas,
            "template": {"spec": pod_spec},
        }
    }


def _namespace(name: str, is_tenant: bool = True) -> dict[str, Any]:
    labels = {"saasphere.io/tenant": "true"} if is_tenant else {}
    return {"metadata": {"name": name, "labels": labels}}


_FALLBACK_TAINT = {
    "key": "saasphere/role",
    "value": "fallback",
    "effect": "NoSchedule",
}
_FALLBACK_TOLERATION = {
    "key": "saasphere/role",
    "operator": "Equal",
    "value": "fallback",
    "effect": "NoSchedule",
}


class FakeK8sClient:
    def __init__(
        self,
        node_selector: dict[str, str] | None = None,
        tolerations: list[dict[str, str]] | None = None,
        node_taints: dict[str, list[dict[str, str]]] | None = None,
        raise_on_get: bool = False,
    ) -> None:
        self._node_selector = node_selector
        self._tolerations = tolerations or []
        self._node_taints = node_taints or {
            "fallback": [_FALLBACK_TAINT],
            "matrix": [],
        }
        self._raise_on_get = raise_on_get
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    async def get_deployment(self, namespace: str, name: str) -> object:
        if self._raise_on_get:
            raise K8sClientError(f"deployment not found: {namespace}/{name}")
        return _deployment(node_selector=self._node_selector)

    async def get_namespace(self, name: str) -> object:
        return _namespace(name)

    async def get_deployment_node_selector(
        self, namespace: str, name: str
    ) -> dict[str, str] | None:
        return self._node_selector

    async def get_deployment_tolerations(self, namespace: str, name: str) -> list[dict[str, str]]:
        return list(self._tolerations)

    async def get_node_taints(self, name: str) -> list[dict[str, str]]:
        return list(self._node_taints.get(name, []))

    async def patch_deployment_placement(
        self,
        namespace: str,
        name: str,
        node_selector: dict[str, str] | None,
        tolerations: list[dict[str, str]] | None,
    ) -> None:
        self.calls.append(
            ("patch_deployment_placement", (namespace, name, node_selector, tolerations))
        )


class FakeMutationContext:
    def __init__(self, status: ActionStatus = ActionStatus.COMPLETED) -> None:
        self.calls: list[dict[str, Any]] = []
        self._status = status

    async def execute(
        self,
        action_type: str,
        namespace: str,
        target: str,
        payload: dict[str, Any],
        manifest: dict[str, Any] | None,
        executor: Any,
        dry_run_override: bool | None = None,
        severity_override: ActionSeverity | None = None,
    ) -> ActionResult:
        self.calls.append(
            {
                "action_type": action_type,
                "namespace": namespace,
                "target": target,
                "severity_override": severity_override,
                "payload": payload,
            }
        )
        if self._status != ActionStatus.ABORTED_DRY_RUN:
            data = await executor()
        else:
            data = None
        return ActionResult(
            action_id="fake-id",
            status=self._status,
            message=f"action {action_type} {self._status.value}",
            data=data,
        )


def _make_ctx(
    k8s: FakeK8sClient,
    mutation_ctx: FakeMutationContext | None = None,
) -> RunContext[AgentDeps]:
    deps = AgentDeps(
        k8s=k8s,  # type: ignore[arg-type]
        prometheus=None,  # type: ignore[arg-type]
        loki=None,  # type: ignore[arg-type]
        alertmanager=None,  # type: ignore[arg-type]
        decisions_repo=None,  # type: ignore[arg-type]
        mutation_context=mutation_ctx,
        action_repo_factory=None,
        approval_manager=None,
        notifier=None,  # type: ignore[arg-type]
    )
    ctx = RunContext.__new__(RunContext)
    object.__setattr__(ctx, "deps", deps)
    return ctx  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# pin_deployment_to_node
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pin_deployment_to_fallback_adds_toleration() -> None:
    k8s = FakeK8sClient()
    mutation_ctx = FakeMutationContext()
    ctx = _make_ctx(k8s, mutation_ctx)

    result = await pin_deployment_to_node(ctx, "tenant-x", "web", "fallback")

    assert "completed" in result
    assert len(mutation_ctx.calls) == 1
    call = mutation_ctx.calls[0]
    assert call["action_type"] == "pin_deployment_to_node"
    assert call["severity_override"] is None
    assert len(k8s.calls) == 1
    method, args = k8s.calls[0]
    assert method == "patch_deployment_placement"
    _, _, node_selector, tolerations = args
    assert node_selector == {"kubernetes.io/hostname": "fallback"}
    assert tolerations is not None
    assert _FALLBACK_TOLERATION in tolerations


@pytest.mark.asyncio
async def test_pin_deployment_to_matrix_no_taint_no_toleration() -> None:
    k8s = FakeK8sClient(node_taints={"matrix": [], "fallback": [_FALLBACK_TAINT]})
    mutation_ctx = FakeMutationContext()
    ctx = _make_ctx(k8s, mutation_ctx)

    await pin_deployment_to_node(ctx, "tenant-x", "web", "matrix")

    _, args = k8s.calls[0]
    _, _, node_selector, tolerations = args
    assert node_selector == {"kubernetes.io/hostname": "matrix"}
    assert tolerations is None


@pytest.mark.asyncio
async def test_pin_deployment_preserves_existing_tolerations() -> None:
    existing_tol = [
        {"key": "node.kubernetes.io/disk-pressure", "operator": "Exists", "effect": "NoSchedule"}
    ]
    k8s = FakeK8sClient(tolerations=existing_tol)
    mutation_ctx = FakeMutationContext()
    ctx = _make_ctx(k8s, mutation_ctx)

    await pin_deployment_to_node(ctx, "tenant-x", "web", "fallback")

    _, args = k8s.calls[0]
    _, _, _, tolerations = args
    assert existing_tol[0] in tolerations
    assert _FALLBACK_TOLERATION in tolerations


@pytest.mark.asyncio
async def test_pin_deployment_to_node_no_mutation_context() -> None:
    k8s = FakeK8sClient()
    ctx = _make_ctx(k8s, mutation_ctx=None)

    result = await pin_deployment_to_node(ctx, "tenant-x", "web", "fallback")

    assert "unavailable" in result
    assert k8s.calls == []


@pytest.mark.asyncio
async def test_pin_deployment_to_node_k8s_error_pre_action() -> None:
    k8s = FakeK8sClient(raise_on_get=True)
    mutation_ctx = FakeMutationContext()
    ctx = _make_ctx(k8s, mutation_ctx)

    result = await pin_deployment_to_node(ctx, "tenant-x", "web", "fallback")

    assert "failed before action creation" in result
    assert mutation_ctx.calls == []


@pytest.mark.asyncio
async def test_pin_deployment_to_node_dry_run_mentions_toleration() -> None:
    k8s = FakeK8sClient()
    mutation_ctx = FakeMutationContext(status=ActionStatus.ABORTED_DRY_RUN)
    ctx = _make_ctx(k8s, mutation_ctx)

    result = await pin_deployment_to_node(ctx, "tenant-x", "web", "fallback")

    assert "would set nodeSelector" in result
    assert "kubernetes.io/hostname" in result
    assert "tolerations" in result
    assert k8s.calls == []


@pytest.mark.asyncio
async def test_pin_deployment_records_previous_state_in_payload() -> None:
    existing_sel = {"kubernetes.io/hostname": "matrix"}
    existing_tol = [{"key": "foo", "operator": "Equal", "value": "bar", "effect": "NoSchedule"}]
    k8s = FakeK8sClient(node_selector=existing_sel, tolerations=existing_tol)
    mutation_ctx = FakeMutationContext()
    ctx = _make_ctx(k8s, mutation_ctx)

    await pin_deployment_to_node(ctx, "tenant-x", "web", "fallback")

    payload = mutation_ctx.calls[0]["payload"]
    assert payload["previous_node_selector"] == existing_sel
    assert payload["previous_tolerations"] == existing_tol
    assert payload["target_node"] == "fallback"
    assert _FALLBACK_TOLERATION in payload["added_tolerations"]


# ---------------------------------------------------------------------------
# unpin_deployment_from_node
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unpin_deployment_strips_saasphere_tolerations() -> None:
    existing_sel = {"kubernetes.io/hostname": "fallback"}
    existing_tol = [
        _FALLBACK_TOLERATION,
        {"key": "user/foo", "operator": "Exists", "effect": "NoSchedule"},
    ]
    k8s = FakeK8sClient(node_selector=existing_sel, tolerations=existing_tol)
    mutation_ctx = FakeMutationContext()
    ctx = _make_ctx(k8s, mutation_ctx)

    result = await unpin_deployment_from_node(ctx, "tenant-x", "web")

    assert "completed" in result
    assert len(k8s.calls) == 1
    method, args = k8s.calls[0]
    assert method == "patch_deployment_placement"
    _, _, node_selector, tolerations = args
    assert node_selector is None
    assert _FALLBACK_TOLERATION not in tolerations
    assert {"key": "user/foo", "operator": "Exists", "effect": "NoSchedule"} in tolerations


@pytest.mark.asyncio
async def test_unpin_deployment_from_node_already_free() -> None:
    k8s = FakeK8sClient(node_selector=None)
    mutation_ctx = FakeMutationContext()
    ctx = _make_ctx(k8s, mutation_ctx)

    result = await unpin_deployment_from_node(ctx, "tenant-x", "web")

    assert "nothing to remove" in result
    assert mutation_ctx.calls == []
    assert k8s.calls == []


@pytest.mark.asyncio
async def test_unpin_deployment_from_node_no_mutation_context() -> None:
    k8s = FakeK8sClient(node_selector={"kubernetes.io/hostname": "fallback"})
    ctx = _make_ctx(k8s, mutation_ctx=None)

    result = await unpin_deployment_from_node(ctx, "tenant-x", "web")

    assert "unavailable" in result


@pytest.mark.asyncio
async def test_unpin_deployment_from_node_autonomous_severity() -> None:
    k8s = FakeK8sClient(
        node_selector={"kubernetes.io/hostname": "fallback"},
        tolerations=[_FALLBACK_TOLERATION],
    )
    mutation_ctx = FakeMutationContext()
    ctx = _make_ctx(k8s, mutation_ctx)

    await unpin_deployment_from_node(ctx, "tenant-x", "web")

    assert mutation_ctx.calls[0]["severity_override"] == ActionSeverity.AUTONOMOUS


@pytest.mark.asyncio
async def test_unpin_deployment_from_node_dry_run() -> None:
    k8s = FakeK8sClient(
        node_selector={"kubernetes.io/hostname": "fallback"},
        tolerations=[_FALLBACK_TOLERATION],
    )
    mutation_ctx = FakeMutationContext(status=ActionStatus.ABORTED_DRY_RUN)
    ctx = _make_ctx(k8s, mutation_ctx)

    result = await unpin_deployment_from_node(ctx, "tenant-x", "web")

    assert "would remove nodeSelector" in result
    assert k8s.calls == []


@pytest.mark.asyncio
async def test_unpin_deployment_k8s_error_pre_action() -> None:
    k8s = FakeK8sClient(node_selector={"kubernetes.io/hostname": "fallback"}, raise_on_get=True)
    mutation_ctx = FakeMutationContext()
    ctx = _make_ctx(k8s, mutation_ctx)

    result = await unpin_deployment_from_node(ctx, "tenant-x", "web")

    assert "failed before action creation" in result
    assert mutation_ctx.calls == []

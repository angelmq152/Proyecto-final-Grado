from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from typing import Any, cast

from pydantic_ai import RunContext
from pydantic_ai.models.test import TestModel

from lobster_agent.agent.deps import AgentDeps
from lobster_agent.agent.mutations import ActionResult
from lobster_agent.agent.orchestrator import LobsterAgent
from lobster_agent.agent.routing import CaseUse
from lobster_agent.agent.tools.mutations.k8s import restart_pod
from lobster_agent.clients.alertmanager import AlertmanagerClient
from lobster_agent.clients.k8s import K8sClient, K8sClientError
from lobster_agent.clients.loki import LokiClient
from lobster_agent.clients.prometheus import PrometheusClient
from lobster_agent.domain.severity import ActionSeverity
from lobster_agent.persistence.db import create_db_engine, create_db_schema, create_sessionmaker
from lobster_agent.persistence.models import ActionStatus
from lobster_agent.persistence.repositories import DecisionRepository
from tests.conftest import make_test_settings


class FakeK8sClient:
    def __init__(
        self,
        *,
        pod: dict[str, Any] | None,
        namespace_labels: dict[str, str] | None = None,
    ) -> None:
        self.pod = pod
        self.namespace_labels = namespace_labels or {"saasphere.io/tenant": "true"}
        self.deleted: list[tuple[str, str]] = []

    async def get_pod(self, namespace: str, name: str) -> object:
        if self.pod is None:
            raise K8sClientError(f"pod not found: {namespace}/{name}")
        return self.pod

    async def get_namespace(self, name: str) -> object:
        return {"metadata": {"name": name, "labels": self.namespace_labels}}

    async def delete_pod(self, namespace: str, name: str) -> None:
        self.deleted.append((namespace, name))


class FakeMutationContext:
    def __init__(self, status: ActionStatus = ActionStatus.COMPLETED) -> None:
        self.status = status
        self.calls: list[dict[str, Any]] = []
        self.approval_requested = False

    async def execute(
        self,
        action_type: str,
        namespace: str,
        target: str,
        payload: dict[str, Any],
        manifest: dict[str, Any] | None,
        executor: Callable[[], Awaitable[Any]],
        dry_run_override: bool | None = None,
        severity_override: ActionSeverity | None = None,
    ) -> ActionResult:
        del manifest, dry_run_override
        self.calls.append(
            {
                "action_type": action_type,
                "namespace": namespace,
                "target": target,
                "payload": payload,
                "severity": severity_override,
            }
        )
        if namespace == "kube-system":
            return ActionResult(
                action_id="a1",
                status=ActionStatus.ABORTED_POLICY,
                message="system namespace is protected",
            )
        if self.status == ActionStatus.ABORTED_DRY_RUN:
            return ActionResult(
                action_id="a1",
                status=ActionStatus.ABORTED_DRY_RUN,
                message="dry run; mutation skipped",
            )
        if severity_override == ActionSeverity.NORMAL:
            self.approval_requested = True
        await executor()
        return ActionResult(action_id="a1", status=self.status, message="completed")


class RestartPodCallingTestModel(TestModel):
    def gen_tool_args(self, tool_def: Any) -> Any:
        if getattr(tool_def, "name", "") == "restart_pod":
            return {"namespace": "tenant-x", "pod_name": "pod-a"}
        return super().gen_tool_args(tool_def)


async def test_agent_chat_restart_request_invokes_restart_pod(tmp_path) -> None:
    db_path = tmp_path / "state.db"
    settings = make_test_settings(database={"url": f"sqlite+aiosqlite:///{db_path}"})
    engine = create_db_engine(settings.database.url)
    await create_db_schema(engine)
    session_maker = create_sessionmaker(engine)
    k8s = FakeK8sClient(pod=_pod(reason=None))
    mutations = FakeMutationContext()

    deps = AgentDeps(
        prometheus=cast(PrometheusClient, SimpleNamespace()),
        loki=cast(LokiClient, SimpleNamespace()),
        k8s=cast(K8sClient, k8s),
        alertmanager=cast(AlertmanagerClient, SimpleNamespace()),
        decisions_repo=DecisionRepository(session_maker),
        mutation_context=cast(Any, mutations),
    )
    model = RestartPodCallingTestModel(
        call_tools=["restart_pod"],
        custom_output_text="restart requested",
    )
    agent = LobsterAgent(settings, deps=deps, model_factory=lambda _model, _think: model)
    result = await agent.run(
        CaseUse.CHAT,
        "Reinicia el pod pod-a en el namespace tenant-x",
    )
    await agent.close()

    assert result.outcome == "success"
    assert mutations.calls[0]["action_type"] == "restart_pod"
    assert mutations.calls[0]["namespace"] == "tenant-x"
    assert mutations.calls[0]["target"] == "pod-a"
    assert k8s.deleted == [("tenant-x", "pod-a")]
    await engine.dispose()


async def test_restart_pod_crashloop_tenant_is_autonomous() -> None:
    k8s = FakeK8sClient(pod=_pod(reason="CrashLoopBackOff"))
    mutations = FakeMutationContext()

    result = await restart_pod(_ctx(k8s, mutations), "tenant-x", "pod-a")

    assert result == "completed"
    assert mutations.calls[0]["severity"] == ActionSeverity.AUTONOMOUS
    assert k8s.deleted == [("tenant-x", "pod-a")]


async def test_restart_pod_running_tenant_requires_normal_approval() -> None:
    k8s = FakeK8sClient(pod=_pod(reason=None))
    mutations = FakeMutationContext()

    result = await restart_pod(_ctx(k8s, mutations), "tenant-x", "pod-a")

    assert result == "completed"
    assert mutations.calls[0]["severity"] == ActionSeverity.NORMAL
    assert mutations.approval_requested is True
    assert k8s.deleted == [("tenant-x", "pod-a")]


async def test_restart_pod_not_found_creates_no_action() -> None:
    k8s = FakeK8sClient(pod=None)
    mutations = FakeMutationContext()

    result = await restart_pod(_ctx(k8s, mutations), "tenant-x", "missing")

    assert "failed before action creation" in result
    assert "pod not found" in result
    assert mutations.calls == []
    assert k8s.deleted == []


async def test_restart_pod_kube_system_policy_rejects_without_executor() -> None:
    k8s = FakeK8sClient(pod=_pod(reason="CrashLoopBackOff"))
    mutations = FakeMutationContext()

    result = await restart_pod(_ctx(k8s, mutations), "kube-system", "coredns")

    assert result == "system namespace is protected"
    assert mutations.calls[0]["namespace"] == "kube-system"
    assert k8s.deleted == []


async def test_restart_pod_dry_run_does_not_call_executor() -> None:
    k8s = FakeK8sClient(pod=_pod(reason="CrashLoopBackOff"))
    mutations = FakeMutationContext(status=ActionStatus.ABORTED_DRY_RUN)

    result = await restart_pod(_ctx(k8s, mutations), "tenant-x", "pod-a")

    assert "dry run" in result
    assert "would delete pod" in result
    assert k8s.deleted == []


async def test_restart_pod_standalone_pod_warns_but_proceeds() -> None:
    k8s = FakeK8sClient(pod=_pod(reason=None, owner=False))
    mutations = FakeMutationContext()

    result = await restart_pod(_ctx(k8s, mutations), "tenant-x", "pod-a")

    assert "standalone pod has no owner" in result
    assert mutations.approval_requested is True
    assert k8s.deleted == [("tenant-x", "pod-a")]


def _ctx(k8s: FakeK8sClient, mutations: FakeMutationContext) -> RunContext[AgentDeps]:
    deps = AgentDeps(
        prometheus=cast(PrometheusClient, SimpleNamespace()),
        loki=cast(LokiClient, SimpleNamespace()),
        k8s=cast(K8sClient, k8s),
        alertmanager=cast(AlertmanagerClient, SimpleNamespace()),
        decisions_repo=cast(DecisionRepository, SimpleNamespace()),
        mutation_context=cast(Any, mutations),
    )
    return cast(RunContext[AgentDeps], SimpleNamespace(deps=deps))


def _pod(reason: str | None, owner: bool = True) -> dict[str, Any]:
    metadata: dict[str, Any] = {"name": "pod-a", "namespace": "tenant-x"}
    if owner:
        metadata["ownerReferences"] = [{"kind": "ReplicaSet", "name": "app-abc123"}]
    state = {"waiting": {"reason": reason}} if reason is not None else {"running": {}}
    return {
        "metadata": metadata,
        "status": {
            "phase": "Running",
            "containerStatuses": [
                {
                    "name": "app",
                    "ready": reason is None,
                    "restartCount": 3 if reason == "CrashLoopBackOff" else 0,
                    "state": state,
                }
            ],
        },
    }

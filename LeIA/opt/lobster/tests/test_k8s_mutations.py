import json
from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from typing import Any, cast

from pydantic_ai import RunContext

from lobster_agent.agent.deps import AgentDeps
from lobster_agent.agent.mutations import ActionResult
from lobster_agent.agent.tools.mutations.k8s import (
    apply_manifest,
    delete_pod_persistent,
    restart_deployment,
    scale_deployment,
    update_configmap,
)
from lobster_agent.clients.alertmanager import AlertmanagerClient
from lobster_agent.clients.k8s import K8sClient, K8sClientError
from lobster_agent.clients.loki import LokiClient
from lobster_agent.clients.prometheus import PrometheusClient
from lobster_agent.domain import policy
from lobster_agent.domain.severity import ActionSeverity
from lobster_agent.persistence.models import Action, ActionStatus
from lobster_agent.persistence.repositories import ActionRepository, DecisionRepository


class FakeK8sClient:
    def __init__(self) -> None:
        self.deployments: dict[tuple[str, str], dict[str, Any]] = {
            ("tenant-x", "web"): _deployment("web")
        }
        self.pods: dict[tuple[str, str], dict[str, Any]] = {
            ("tenant-x", "standalone"): _pod(owner=False),
            ("tenant-x", "owned"): _pod(owner=True),
        }
        self.namespace_labels: dict[str, dict[str, str]] = {
            "tenant-x": {"saasphere.io/tenant": "true"},
            "kube-system": {},
        }
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    async def get_deployment(self, namespace: str, name: str) -> object:
        deployment = self.deployments.get((namespace, name))
        if deployment is None:
            raise K8sClientError(f"deployment not found: {namespace}/{name}")
        return deployment

    async def get_pod(self, namespace: str, name: str) -> object:
        pod = self.pods.get((namespace, name))
        if pod is None:
            raise K8sClientError(f"pod not found: {namespace}/{name}")
        return pod

    async def get_namespace(self, name: str) -> object:
        return {"metadata": {"name": name, "labels": self.namespace_labels.get(name, {})}}

    async def restart_deployment(self, namespace: str, name: str) -> None:
        self.calls.append(("restart_deployment", (namespace, name)))

    async def scale_deployment(self, namespace: str, name: str, replicas: int) -> None:
        self.calls.append(("scale_deployment", (namespace, name, replicas)))

    async def delete_pod(self, namespace: str, name: str, force: bool = False) -> None:
        self.calls.append(("delete_pod", (namespace, name, force)))

    async def apply_manifest(self, yaml_text: str) -> dict[str, str]:
        self.calls.append(("apply_manifest", (yaml_text,)))
        return {"kind": "Deployment", "namespace": "tenant-x", "name": "web", "action": "updated"}

    async def update_configmap(self, namespace: str, name: str, data: dict[str, str]) -> None:
        self.calls.append(("update_configmap", (namespace, name, data)))


class FakeActionRepository:
    def __init__(self, prior_scale_zero: bool = False) -> None:
        self.prior_scale_zero = prior_scale_zero

    async def list_recent(
        self,
        limit: int = 20,
        status: ActionStatus | None = None,
    ) -> list[Action]:
        del limit, status
        if not self.prior_scale_zero:
            return []
        return [
            Action(
                action_type="scale_deployment",
                namespace="tenant-x",
                target="web",
                severity=ActionSeverity.CRITICAL.value,
                status=ActionStatus.COMPLETED.value,
                payload=json.dumps({"target_replicas": 0}),
            )
        ]


class FakeMutationContext:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

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
        del dry_run_override
        self.calls.append(
            {
                "action_type": action_type,
                "namespace": namespace,
                "target": target,
                "payload": payload,
                "manifest": manifest,
                "severity": severity_override,
            }
        )
        decision = policy.validate(action_type, namespace, manifest=manifest, context=payload)
        if not decision.allowed:
            return ActionResult(
                action_id="a1",
                status=ActionStatus.ABORTED_POLICY,
                message=decision.reason,
            )
        await executor()
        return ActionResult(action_id="a1", status=ActionStatus.COMPLETED, message="completed")


async def test_restart_deployment_executes_normal() -> None:
    k8s = FakeK8sClient()
    mutations = FakeMutationContext()

    result = await restart_deployment(_ctx(k8s, mutations), "tenant-x", "web")

    assert result == "completed"
    assert mutations.calls[0]["severity"] == ActionSeverity.NORMAL
    assert ("restart_deployment", ("tenant-x", "web")) in k8s.calls


async def test_restart_deployment_not_found_creates_no_action() -> None:
    k8s = FakeK8sClient()
    mutations = FakeMutationContext()

    result = await restart_deployment(_ctx(k8s, mutations), "tenant-x", "missing")

    assert "failed before action creation" in result
    assert mutations.calls == []


async def test_scale_deployment_positive_executes_normal() -> None:
    k8s = FakeK8sClient()
    mutations = FakeMutationContext()

    result = await scale_deployment(_ctx(k8s, mutations), "tenant-x", "web", 3)

    assert result == "completed"
    assert mutations.calls[0]["severity"] == ActionSeverity.NORMAL
    assert ("scale_deployment", ("tenant-x", "web", 3)) in k8s.calls


async def test_scale_deployment_zero_first_time_is_critical() -> None:
    k8s = FakeK8sClient()
    mutations = FakeMutationContext()

    result = await scale_deployment(_ctx(k8s, mutations), "tenant-x", "web", 0)

    assert result == "completed"
    assert mutations.calls[0]["severity"] == ActionSeverity.CRITICAL


async def test_scale_deployment_zero_second_time_is_normal() -> None:
    k8s = FakeK8sClient()
    mutations = FakeMutationContext()

    result = await scale_deployment(
        _ctx(k8s, mutations, prior_scale_zero=True),
        "tenant-x",
        "web",
        0,
    )

    assert result == "completed"
    assert mutations.calls[0]["severity"] == ActionSeverity.NORMAL


async def test_scale_deployment_negative_replica_count_creates_no_action() -> None:
    k8s = FakeK8sClient()
    mutations = FakeMutationContext()

    result = await scale_deployment(_ctx(k8s, mutations), "tenant-x", "web", -1)

    assert "replicas must be >= 0" in result
    assert mutations.calls == []
    assert k8s.calls == []


async def test_delete_pod_persistent_without_owner_executes() -> None:
    k8s = FakeK8sClient()
    mutations = FakeMutationContext()

    result = await delete_pod_persistent(_ctx(k8s, mutations), "tenant-x", "standalone")

    assert result == "completed"
    assert mutations.calls[0]["severity"] == ActionSeverity.NORMAL
    assert ("delete_pod", ("tenant-x", "standalone", False)) in k8s.calls


async def test_delete_pod_persistent_with_owner_warns_and_executes() -> None:
    k8s = FakeK8sClient()
    mutations = FakeMutationContext()

    result = await delete_pod_persistent(_ctx(k8s, mutations), "tenant-x", "owned")

    assert "will be recreated" in result
    assert mutations.calls[0]["severity"] == ActionSeverity.NORMAL
    assert ("delete_pod", ("tenant-x", "owned", False)) in k8s.calls


async def test_apply_manifest_valid_deployment_executes() -> None:
    k8s = FakeK8sClient()
    mutations = FakeMutationContext()

    result = await apply_manifest(_ctx(k8s, mutations), _deployment_yaml())

    assert result == "completed"
    assert mutations.calls[0]["severity"] == ActionSeverity.NORMAL
    assert any(call[0] == "apply_manifest" for call in k8s.calls)


async def test_apply_manifest_privileged_aborts_policy() -> None:
    k8s = FakeK8sClient()
    mutations = FakeMutationContext()

    result = await apply_manifest(_ctx(k8s, mutations), _deployment_yaml(privileged=True))

    assert "privileged" in result
    assert k8s.calls == []


async def test_apply_manifest_host_path_aborts_policy() -> None:
    k8s = FakeK8sClient()
    mutations = FakeMutationContext()

    result = await apply_manifest(_ctx(k8s, mutations), _deployment_yaml(host_path=True))

    assert "hostPath" in result
    assert k8s.calls == []


async def test_apply_manifest_missing_limits_aborts_policy() -> None:
    k8s = FakeK8sClient()
    mutations = FakeMutationContext()

    result = await apply_manifest(_ctx(k8s, mutations), _deployment_yaml(limits=False))

    assert "resource limits" in result
    assert k8s.calls == []


async def test_apply_manifest_secret_aborts_policy() -> None:
    k8s = FakeK8sClient()
    mutations = FakeMutationContext()

    result = await apply_manifest(_ctx(k8s, mutations), _secret_yaml())

    assert "forbidden" in result
    assert k8s.calls == []


async def test_apply_manifest_multi_doc_creates_no_action() -> None:
    k8s = FakeK8sClient()
    mutations = FakeMutationContext()

    result = await apply_manifest(_ctx(k8s, mutations), f"{_secret_yaml()}---\n{_secret_yaml()}")

    assert "multi-document" in result
    assert mutations.calls == []


async def test_apply_manifest_invalid_yaml_creates_no_action() -> None:
    k8s = FakeK8sClient()
    mutations = FakeMutationContext()

    result = await apply_manifest(_ctx(k8s, mutations), "kind: [")

    assert "invalid YAML syntax" in result
    assert mutations.calls == []


async def test_update_configmap_executes_normal() -> None:
    k8s = FakeK8sClient()
    mutations = FakeMutationContext()

    result = await update_configmap(_ctx(k8s, mutations), "tenant-x", "settings", {"a": "b"})

    assert result == "completed"
    assert mutations.calls[0]["severity"] == ActionSeverity.NORMAL
    assert ("update_configmap", ("tenant-x", "settings", {"a": "b"})) in k8s.calls


async def test_update_configmap_kube_system_aborts_policy() -> None:
    k8s = FakeK8sClient()
    mutations = FakeMutationContext()

    result = await update_configmap(_ctx(k8s, mutations), "kube-system", "settings", {"a": "b"})

    assert "namespace is hard-blocked" in result
    assert k8s.calls == []


def _ctx(
    k8s: FakeK8sClient,
    mutations: FakeMutationContext,
    *,
    prior_scale_zero: bool = False,
) -> RunContext[AgentDeps]:
    async def action_repo_factory() -> ActionRepository:
        return cast(ActionRepository, FakeActionRepository(prior_scale_zero))

    deps = AgentDeps(
        prometheus=cast(PrometheusClient, SimpleNamespace()),
        loki=cast(LokiClient, SimpleNamespace()),
        k8s=cast(K8sClient, k8s),
        alertmanager=cast(AlertmanagerClient, SimpleNamespace()),
        decisions_repo=cast(DecisionRepository, SimpleNamespace()),
        action_repo_factory=action_repo_factory,
        mutation_context=cast(Any, mutations),
    )
    return cast(RunContext[AgentDeps], SimpleNamespace(deps=deps))


def _deployment(name: str) -> dict[str, Any]:
    return {
        "metadata": {"name": name, "namespace": "tenant-x"},
        "spec": {"replicas": 2},
        "status": {"readyReplicas": 2, "availableReplicas": 2},
    }


def _pod(*, owner: bool) -> dict[str, Any]:
    metadata: dict[str, Any] = {"name": "pod", "namespace": "tenant-x"}
    if owner:
        metadata["ownerReferences"] = [{"kind": "Deployment", "name": "web"}]
    return {
        "metadata": metadata,
        "status": {
            "phase": "Running",
            "containerStatuses": [{"name": "app", "ready": True, "restartCount": 0}],
        },
    }


def _deployment_yaml(
    *,
    privileged: bool = False,
    host_path: bool = False,
    limits: bool = True,
) -> str:
    resources = (
        "        resources:\n          limits:\n            cpu: 100m\n            memory: 128Mi\n"
        if limits
        else ""
    )
    security = "        securityContext:\n          privileged: true\n" if privileged else ""
    volumes = (
        "      volumes:\n"
        "        - name: host\n"
        "          hostPath:\n"
        "            path: /var/run/docker.sock\n"
        if host_path
        else ""
    )
    return (
        "apiVersion: apps/v1\n"
        "kind: Deployment\n"
        "metadata:\n"
        "  name: web\n"
        "  namespace: tenant-x\n"
        "spec:\n"
        "  template:\n"
        "    spec:\n"
        f"{volumes}"
        "      containers:\n"
        "      - name: web\n"
        "        image: nginx\n"
        f"{security}"
        f"{resources}"
    )


def _secret_yaml() -> str:
    return "apiVersion: v1\nkind: Secret\nmetadata:\n  name: s\n  namespace: tenant-x\n"

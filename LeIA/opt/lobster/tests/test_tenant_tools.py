from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

import yaml
from pydantic_ai import RunContext

from lobster_agent.agent.deps import AgentDeps
from lobster_agent.agent.mutations import ActionResult
from lobster_agent.agent.tools.mutations.tenant import (
    delete_tenant,
    deploy_tenant,
    pause_tenant,
    resume_tenant,
    verify_tenant_health,
)
from lobster_agent.clients.alertmanager import AlertmanagerClient
from lobster_agent.clients.k8s import K8sClient, K8sClientError
from lobster_agent.clients.loki import LokiClient
from lobster_agent.clients.prometheus import PrometheusClient
from lobster_agent.domain.severity import ActionSeverity
from lobster_agent.persistence.models import ActionStatus
from lobster_agent.persistence.repositories import DecisionRepository


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
        try:
            data = await executor()
        except Exception as exc:
            return ActionResult("a1", ActionStatus.FAILED, str(exc), {"error": str(exc)})
        return ActionResult("a1", ActionStatus.COMPLETED, "completed", data)


class FakeK8sClient:
    def __init__(self) -> None:
        self.applied: list[dict[str, Any]] = []
        self.deleted_namespaces: list[str] = []
        self.scaled: list[tuple[str, str, int]] = []
        self.annotations: dict[str, str] = {}
        self.fail_apply_index: int | None = None
        self.deployments = [_deployment("web", 1)]
        self.pods = [_pod("web-1", None)]
        self.pvcs = [_pvc("data", "Bound")]
        self.ingresses = [
            {
                "name": "web",
                "namespace": "tenant-x",
                "hosts": ["tenant-x.example.com"],
                "tls": True,
                "address": "192.0.2.10",
                "age_minutes": 5,
            }
        ]
        self.tenant_labels = {"saasphere.io/tenant": "true"}
        self.pvc_bound: bool = True
        self.storage_response: dict[str, str | None] = {
            "path": "/var/lib/rancher/k3s/storage/pvc-default",
            "node": "matrix",
            "pv_name": "pvc-default",
        }

    async def apply_manifest(self, yaml_text: str) -> dict[str, str]:
        if self.fail_apply_index is not None and len(self.applied) == self.fail_apply_index:
            raise K8sClientError("apply failed")
        manifest = yaml.safe_load(yaml_text)
        self.applied.append(manifest)
        metadata = manifest.get("metadata", {})
        return {
            "kind": manifest["kind"],
            "namespace": metadata.get("namespace", metadata.get("name", "")),
            "name": metadata.get("name", ""),
            "action": "created",
        }

    async def wait_for_pvc_bound(
        self,
        namespace: str,
        pvc_name: str,
        timeout_seconds: int = 30,
    ) -> bool:
        del namespace, pvc_name, timeout_seconds
        return self.pvc_bound

    async def get_pvc_storage_path(
        self,
        namespace: str,
        pvc_name: str,
    ) -> dict[str, str | None]:
        del namespace, pvc_name
        return dict(self.storage_response)

    async def delete_namespace(self, namespace: str) -> None:
        self.deleted_namespaces.append(namespace)

    async def get_namespace(self, namespace: str) -> object:
        if self.tenant_labels.get("saasphere.io/tenant") != "true":
            return {"metadata": {"name": namespace, "labels": {}}}
        return {"metadata": {"name": namespace, "labels": self.tenant_labels}}

    async def list_deployments(self, namespace: str) -> list[object]:
        del namespace
        return list(self.deployments)

    async def patch_namespace_annotations(
        self,
        namespace: str,
        annotations: dict[str, str],
    ) -> None:
        del namespace
        self.annotations.update(annotations)

    async def scale_deployment(self, namespace: str, name: str, replicas: int) -> None:
        self.scaled.append((namespace, name, replicas))

    async def get_namespace_annotations(self, namespace: str) -> dict[str, str]:
        del namespace
        return dict(self.annotations)

    async def list_pods(self, namespace: str) -> list[object]:
        del namespace
        return list(self.pods)

    async def list_ingresses(self, namespace: str) -> list[dict[str, Any]]:
        del namespace
        return list(self.ingresses)

    async def list_pvcs(self, namespace: str) -> list[object]:
        del namespace
        return list(self.pvcs)


async def test_deploy_static_site_free_creates_critical_action() -> None:
    k8s = FakeK8sClient()
    mutations = FakeMutationContext()

    result = await deploy_tenant(_ctx(k8s, mutations), "static_site", "tenant-x")

    assert "tenant deployed" in result
    assert mutations.calls[0]["severity"] == ActionSeverity.CRITICAL
    assert [item["kind"] for item in k8s.applied][0] == "Namespace"


async def test_deploy_static_site_basic_replicas_one() -> None:
    k8s = FakeK8sClient()
    await deploy_tenant(_ctx(k8s, FakeMutationContext()), "static_site", "tenant-x", tier="basic")
    deployment = next(item for item in k8s.applied if item["kind"] == "Deployment")
    assert deployment["spec"]["replicas"] == 1


async def test_deploy_premium_replicas_two() -> None:
    k8s = FakeK8sClient()
    await deploy_tenant(_ctx(k8s, FakeMutationContext()), "static_site", "tenant-x", tier="premium")
    deployment = next(item for item in k8s.applied if item["kind"] == "Deployment")
    assert deployment["spec"]["replicas"] == 2


async def test_deploy_wordpress_generates_secret_and_deployments() -> None:
    k8s = FakeK8sClient()
    await deploy_tenant(
        _ctx(k8s, FakeMutationContext()),
        "wordpress",
        "tenant-x",
        admin_email="admin@example.com",
    )
    assert any(item["kind"] == "Secret" for item in k8s.applied)
    names = [item["metadata"]["name"] for item in k8s.applied if item["kind"] == "Deployment"]
    assert {"wordpress", "mariadb"} <= set(names)


async def test_deploy_web_app_missing_image_returns_error() -> None:
    mutations = FakeMutationContext()
    result = await deploy_tenant(_ctx(FakeK8sClient(), mutations), "web_app", "tenant-x")
    assert "requires image" in result
    assert mutations.calls == []


async def test_deploy_wordpress_missing_admin_email_returns_error() -> None:
    mutations = FakeMutationContext()
    result = await deploy_tenant(_ctx(FakeK8sClient(), mutations), "wordpress", "tenant-x")
    assert "requires admin_email" in result
    assert mutations.calls == []


async def test_deploy_invalid_name_returns_error() -> None:
    result = await deploy_tenant(
        _ctx(FakeK8sClient(), FakeMutationContext()),
        "static_site",
        "Bad.Name",
    )
    assert "DNS-1123" in result


async def test_deploy_local_hostname_has_no_tls() -> None:
    k8s = FakeK8sClient()
    await deploy_tenant(
        _ctx(k8s, FakeMutationContext()),
        "static_site",
        "tenant-x",
        hostname="tenant-x.saasphere.local",
    )
    ingress = next(item for item in k8s.applied if item["kind"] == "Ingress")
    assert "tls" not in ingress["spec"]


async def test_deploy_real_hostname_has_tls() -> None:
    k8s = FakeK8sClient()
    await deploy_tenant(
        _ctx(k8s, FakeMutationContext()),
        "static_site",
        "tenant-x",
        hostname="example.com",
    )
    ingress = next(item for item in k8s.applied if item["kind"] == "Ingress")
    assert "tls" in ingress["spec"]


async def test_deploy_rollback_deletes_namespace() -> None:
    k8s = FakeK8sClient()
    k8s.fail_apply_index = 1
    result = await deploy_tenant(_ctx(k8s, FakeMutationContext()), "static_site", "tenant-x")
    assert "apply failed" in result
    assert k8s.deleted_namespaces == ["tenant-x"]


async def test_delete_tenant_confirm_match_executes() -> None:
    k8s = FakeK8sClient()
    result = await delete_tenant(_ctx(k8s, FakeMutationContext()), "tenant-x", "tenant-x")
    assert result == "completed"
    assert k8s.deleted_namespaces == ["tenant-x"]


async def test_delete_tenant_confirm_mismatch_no_action() -> None:
    mutations = FakeMutationContext()
    result = await delete_tenant(_ctx(FakeK8sClient(), mutations), "tenant-x", "other")
    assert "confirm_namespace" in result
    assert mutations.calls == []


async def test_delete_tenant_non_tenant_rejected() -> None:
    k8s = FakeK8sClient()
    k8s.tenant_labels = {}
    result = await delete_tenant(_ctx(k8s, FakeMutationContext()), "tenant-x", "tenant-x")
    assert "not a tenant" in result


async def test_pause_tenant_stores_annotation_and_scales_zero() -> None:
    k8s = FakeK8sClient()
    result = await pause_tenant(_ctx(k8s, FakeMutationContext()), "tenant-x")
    assert result == "completed"
    assert k8s.annotations["saasphere.io/paused-replicas-web"] == "1"
    assert k8s.scaled == [("tenant-x", "web", 0)]


async def test_resume_tenant_restores_annotations_autonomous() -> None:
    k8s = FakeK8sClient()
    k8s.annotations = {"saasphere.io/paused-replicas-web": "2"}
    mutations = FakeMutationContext()
    result = await resume_tenant(_ctx(k8s, mutations), "tenant-x")
    assert result == "completed"
    assert mutations.calls[0]["severity"] == ActionSeverity.AUTONOMOUS
    assert k8s.scaled == [("tenant-x", "web", 2)]


async def test_resume_without_pause_returns_error() -> None:
    mutations = FakeMutationContext()
    result = await resume_tenant(_ctx(FakeK8sClient(), mutations), "tenant-x")
    assert "not paused" in result
    assert mutations.calls == []


async def test_verify_tenant_health_ok() -> None:
    result = await verify_tenant_health(_ctx(FakeK8sClient(), FakeMutationContext()), "tenant-x")
    assert result.startswith("ok:")


async def test_verify_tenant_health_includes_ingress_hostname() -> None:
    result = await verify_tenant_health(_ctx(FakeK8sClient(), FakeMutationContext()), "tenant-x")
    assert "tenant-x.example.com" in result
    assert "address_assigned" in result


async def test_verify_tenant_health_warns_without_ingress() -> None:
    k8s = FakeK8sClient()
    k8s.ingresses = []
    result = await verify_tenant_health(_ctx(k8s, FakeMutationContext()), "tenant-x")
    assert "warning" in result
    assert "no ingress configured" in result


async def test_verify_tenant_health_crashloop_warning() -> None:
    k8s = FakeK8sClient()
    k8s.pods = [_pod("web-1", "CrashLoopBackOff")]
    result = await verify_tenant_health(_ctx(k8s, FakeMutationContext()), "tenant-x")
    assert "warning" in result
    assert "CrashLoopBackOff" in result or "crashloop" in result


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


def _deployment(name: str, replicas: int) -> dict[str, Any]:
    return {
        "metadata": {"name": name},
        "spec": {"replicas": replicas},
        "status": {"readyReplicas": replicas},
    }


def _pod(name: str, reason: str | None) -> dict[str, Any]:
    state = {"waiting": {"reason": reason}} if reason else {"running": {}}
    return {"metadata": {"name": name}, "status": {"containerStatuses": [{"state": state}]}}


def _pvc(name: str, phase: str) -> dict[str, Any]:
    return {"metadata": {"name": name}, "status": {"phase": phase}}


async def test_deploy_static_site_message_includes_leia_path() -> None:
    mutations = FakeMutationContext()

    result = await deploy_tenant(_ctx(FakeK8sClient(), mutations), "static_site", "tenant-x")

    assert "leia" in result.lower() or "/srv/k3s-pvs" in result
    assert "tenant-x" in result


def test_pv_node_extracts_hostname_from_node_affinity_dict() -> None:
    from lobster_agent.clients.k8s import _pv_node

    pv_spec = {
        "nodeAffinity": {
            "required": {
                "nodeSelectorTerms": [
                    {
                        "matchExpressions": [
                            {
                                "key": "kubernetes.io/hostname",
                                "operator": "In",
                                "values": ["matrix"],
                            }
                        ]
                    }
                ]
            }
        }
    }
    assert _pv_node(pv_spec) == "matrix"


def test_pv_node_returns_none_without_hostname_expression() -> None:
    from lobster_agent.clients.k8s import _pv_node

    assert _pv_node({}) is None
    assert _pv_node(None) is None
    assert (
        _pv_node({"nodeAffinity": {"required": {"nodeSelectorTerms": [{"matchExpressions": []}]}}})
        is None
    )

from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Literal, Protocol, cast

import structlog
from pydantic_ai import RunContext

from lobster_agent.agent.deps import AgentDeps
from lobster_agent.agent.mutations import ActionResult
from lobster_agent.clients.k8s import K8sClientError
from lobster_agent.domain.severity import ActionSeverity
from lobster_agent.persistence.models import ActionStatus

log = structlog.get_logger()

# Real SaaSphere K3s cluster has two nodes: matrix (control-plane + primary
# workload host) and fallback (cold standby, tainted so K8s won't schedule
# there by default). The other observed hosts (leia, sauron, heimdall) are
# external monitoring targets, not K3s nodes.
KnownNode = Literal["matrix", "fallback"]


class MutationContextLike(Protocol):
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
    ) -> ActionResult: ...


async def pin_deployment_to_node(
    ctx: RunContext[AgentDeps],
    namespace: str,
    deployment_name: str,
    node: KnownNode,
) -> str:
    """
    Pin a Deployment to a specific SaaSphere node by setting nodeSelector and
    adding any tolerations required to schedule on it.

    The 'fallback' node is tainted (saasphere/role=fallback:NoSchedule) so
    Kubernetes will not place pods there unless they explicitly tolerate the
    taint. This tool reads the target node's taints and generates matching
    tolerations alongside the nodeSelector so the pod actually schedules.

    Kubernetes triggers a rolling update automatically. Use this tool when
    matrix is under resource pressure or unreachable and you want to move a
    tenant workload to fallback.

    Severity: NORMAL — requires human approval.
    Safe to call: policy.validate() rejects system namespaces before touching K8s.
    """
    if ctx.deps.mutation_context is None:
        return "pin_deployment_to_node unavailable: mutation context is not configured"

    try:
        deployment = await ctx.deps.k8s.get_deployment(namespace, deployment_name)
        namespace_obj = await ctx.deps.k8s.get_namespace(namespace)
        current_selector = await ctx.deps.k8s.get_deployment_node_selector(
            namespace, deployment_name
        )
        current_tolerations = await ctx.deps.k8s.get_deployment_tolerations(
            namespace, deployment_name
        )
        node_taints = await ctx.deps.k8s.get_node_taints(node)
    except K8sClientError as exc:
        return f"pin_deployment_to_node failed before action creation: {exc}"

    node_selector = {"kubernetes.io/hostname": node}
    required_tolerations = _tolerations_for_taints(node_taints)
    new_tolerations = _merge_tolerations(current_tolerations, required_tolerations)
    tolerations_changed = new_tolerations != current_tolerations

    payload: dict[str, Any] = {
        "namespace": namespace,
        "deployment_name": deployment_name,
        "target_node": node,
        "previous_node_selector": current_selector,
        "new_node_selector": node_selector,
        "previous_tolerations": current_tolerations,
        "added_tolerations": required_tolerations,
        "new_tolerations": new_tolerations,
        "namespace_labels": {namespace: _labels(namespace_obj)},
        "current_replicas": _deployment_replicas(deployment),
    }

    async def executor() -> dict[str, Any]:
        tolerations_arg = new_tolerations if tolerations_changed else None
        await ctx.deps.k8s.patch_deployment_placement(
            namespace, deployment_name, node_selector, tolerations_arg
        )
        return {
            "pinned": True,
            "namespace": namespace,
            "deployment_name": deployment_name,
            "node": node,
            "node_selector": node_selector,
            "tolerations": new_tolerations,
        }

    result = await cast(MutationContextLike, ctx.deps.mutation_context).execute(
        action_type="pin_deployment_to_node",
        namespace=namespace,
        target=deployment_name,
        payload=payload,
        manifest=None,
        executor=executor,
        severity_override=ActionSeverity.NORMAL,
    )
    if result.status == ActionStatus.ABORTED_DRY_RUN:
        extra = ""
        if required_tolerations:
            extra = f" with tolerations {required_tolerations}"
        return f"{result.message}; would set nodeSelector to {node_selector}{extra}."
    return result.message


async def unpin_deployment_from_node(
    ctx: RunContext[AgentDeps],
    namespace: str,
    deployment_name: str,
) -> str:
    """
    Remove the nodeSelector pin from a Deployment and strip any saasphere-managed
    tolerations that were added by pin_deployment_to_node. After unpinning,
    Kubernetes is free to reschedule pods on any eligible node.

    Use this tool after matrix has recovered (Ready + below threshold for a
    sustained window) and you want to restore normal scheduling.

    Severity: AUTONOMOUS — safe without human approval since it relaxes a
    constraint rather than forcing pods to a specific location.
    """
    if ctx.deps.mutation_context is None:
        return "unpin_deployment_from_node unavailable: mutation context is not configured"

    try:
        await ctx.deps.k8s.get_deployment(namespace, deployment_name)
        namespace_obj = await ctx.deps.k8s.get_namespace(namespace)
        current_selector = await ctx.deps.k8s.get_deployment_node_selector(
            namespace, deployment_name
        )
        current_tolerations = await ctx.deps.k8s.get_deployment_tolerations(
            namespace, deployment_name
        )
    except K8sClientError as exc:
        return f"unpin_deployment_from_node failed before action creation: {exc}"

    if current_selector is None:
        return (
            f"Deployment {namespace}/{deployment_name} has no nodeSelector pin — nothing to remove."
        )

    new_tolerations = _strip_saasphere_tolerations(current_tolerations)
    tolerations_changed = new_tolerations != current_tolerations

    payload: dict[str, Any] = {
        "namespace": namespace,
        "deployment_name": deployment_name,
        "removed_node_selector": current_selector,
        "previous_tolerations": current_tolerations,
        "new_tolerations": new_tolerations,
        "namespace_labels": {namespace: _labels(namespace_obj)},
    }

    async def executor() -> dict[str, Any]:
        tolerations_arg = new_tolerations if tolerations_changed else None
        await ctx.deps.k8s.patch_deployment_placement(
            namespace, deployment_name, None, tolerations_arg
        )
        return {
            "unpinned": True,
            "namespace": namespace,
            "deployment_name": deployment_name,
            "removed_selector": current_selector,
            "tolerations": new_tolerations,
        }

    result = await cast(MutationContextLike, ctx.deps.mutation_context).execute(
        action_type="unpin_deployment_from_node",
        namespace=namespace,
        target=deployment_name,
        payload=payload,
        manifest=None,
        executor=executor,
        severity_override=ActionSeverity.AUTONOMOUS,
    )
    if result.status == ActionStatus.ABORTED_DRY_RUN:
        extra = ""
        if tolerations_changed:
            extra = " and clearing saasphere tolerations"
        return f"{result.message}; would remove nodeSelector {current_selector}{extra}."
    return result.message


_SAASPHERE_TAINT_KEY_PREFIX = "saasphere/"


def _tolerations_for_taints(taints: list[dict[str, str]]) -> list[dict[str, str]]:
    tolerations: list[dict[str, str]] = []
    for taint in taints:
        effect = taint.get("effect")
        if effect not in ("NoSchedule", "NoExecute", "PreferNoSchedule"):
            continue
        key = taint.get("key", "")
        value = taint.get("value")
        tol: dict[str, str] = {"key": key, "effect": effect}
        if value is not None:
            tol["operator"] = "Equal"
            tol["value"] = value
        else:
            tol["operator"] = "Exists"
        tolerations.append(tol)
    return tolerations


def _merge_tolerations(
    existing: list[dict[str, str]], extra: list[dict[str, str]]
) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = list(existing)
    for tol in extra:
        if tol not in merged:
            merged.append(tol)
    return merged


def _strip_saasphere_tolerations(
    tolerations: list[dict[str, str]],
) -> list[dict[str, str]]:
    return [
        tol for tol in tolerations if not tol.get("key", "").startswith(_SAASPHERE_TAINT_KEY_PREFIX)
    ]


def _labels(namespace_obj: object) -> dict[str, str]:
    metadata = _get_attr(namespace_obj, "metadata")
    value = _get_attr(metadata, "labels")
    if not isinstance(value, Mapping):
        return {}
    return {
        str(key): str(item)
        for key, item in value.items()
        if isinstance(key, str) and isinstance(item, str)
    }


def _deployment_replicas(deployment: object) -> int | None:
    spec = _get_attr(deployment, "spec")
    value = _get_attr(spec, "replicas")
    return value if isinstance(value, int) else None


def _get_attr(obj: object | None, *names: str) -> object | None:
    if obj is None:
        return None
    for name in names:
        if isinstance(obj, Mapping) and name in obj:
            return obj[name]
        value = getattr(obj, name, None)
        if value is not None:
            return value
    return None

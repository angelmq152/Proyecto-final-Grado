from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, Protocol, cast

import structlog
import yaml
from pydantic_ai import RunContext

from lobster_agent.agent.deps import AgentDeps
from lobster_agent.agent.mutations import ActionResult
from lobster_agent.clients.k8s import K8sClientError
from lobster_agent.domain.severity import ActionSeverity
from lobster_agent.persistence.models import ActionStatus

log = structlog.get_logger()


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


async def restart_pod(
    ctx: RunContext[AgentDeps],
    namespace: str,
    pod_name: str,
) -> str:
    """
    Restart a pod by deleting it. Kubernetes recreates it automatically
    if it has an owner (Deployment, ReplicaSet, StatefulSet).

    Call this tool whenever the user asks to restart, reboot, or fix a pod.
    Call this tool when a pod is in CrashLoopBackOff or Error state and the
    user asks what to do about it or asks to fix it.
    Do NOT respond with a text explanation instead of calling this tool when
    the user requests a pod restart.

    AUTONOMOUS when pod is in CrashLoopBackOff, NORMAL otherwise.
    Safe to call: policy.validate() will reject kube-system and
    non-tenant namespaces before touching K8s.
    """
    log.info(
        "restart_pod.called",
        namespace=namespace,
        pod_name=pod_name,
        mutation_context_present=ctx.deps.mutation_context is not None,
    )
    if ctx.deps.mutation_context is None:
        return "restart_pod unavailable: mutation context is not configured"

    try:
        pod = await ctx.deps.k8s.get_pod(namespace, pod_name)
        namespace_obj = await ctx.deps.k8s.get_namespace(namespace)
    except K8sClientError as exc:
        return f"restart_pod failed before action creation: {exc}"

    labels = _labels(namespace_obj)
    container_statuses = _container_statuses(pod)
    crash_loop = any(status.get("reason") == "CrashLoopBackOff" for status in container_statuses)
    tenant_namespace = labels.get("saasphere.io/tenant") == "true"
    severity = (
        ActionSeverity.AUTONOMOUS if crash_loop and tenant_namespace else ActionSeverity.NORMAL
    )
    owner_refs = _owner_references(pod)
    standalone_warning = (
        "" if owner_refs else " Warning: standalone pod has no owner; it may not be recreated."
    )
    payload: dict[str, Any] = {
        "namespace": namespace,
        "pod_name": pod_name,
        "pod_phase": _pod_phase(pod),
        "container_statuses": container_statuses,
        "namespace_labels": {namespace: labels},
        "owner_references": owner_refs,
    }

    async def executor() -> dict[str, Any]:
        await ctx.deps.k8s.delete_pod(namespace, pod_name)
        return {
            "deleted": True,
            "namespace": namespace,
            "pod_name": pod_name,
            "will_recreate": bool(owner_refs),
        }

    mutation_context = cast(MutationContextLike, ctx.deps.mutation_context)
    result = await mutation_context.execute(
        action_type="restart_pod",
        namespace=namespace,
        target=pod_name,
        payload=payload,
        manifest=None,
        executor=executor,
        severity_override=severity,
    )
    return _message(result, standalone_warning)


def _message(result: ActionResult, suffix: str) -> str:
    if result.status == ActionStatus.ABORTED_DRY_RUN:
        return f"{result.message}; would delete pod to restart it.{suffix}"
    return f"{result.message}{suffix}"


async def restart_deployment(
    ctx: RunContext[AgentDeps],
    namespace: str,
    deployment_name: str,
) -> str:
    """Rolling restart of a Deployment. Always requires approval."""
    if ctx.deps.mutation_context is None:
        return "restart_deployment unavailable: mutation context is not configured"
    try:
        deployment = await ctx.deps.k8s.get_deployment(namespace, deployment_name)
        namespace_obj = await ctx.deps.k8s.get_namespace(namespace)
    except K8sClientError as exc:
        return f"restart_deployment failed before action creation: {exc}"

    payload = {
        "namespace": namespace,
        "deployment_name": deployment_name,
        "current_replicas": _deployment_replicas(deployment),
        "ready_replicas": _deployment_ready_replicas(deployment),
        "available_replicas": _deployment_available_replicas(deployment),
        "namespace_labels": {namespace: _labels(namespace_obj)},
    }

    async def executor() -> dict[str, Any]:
        await ctx.deps.k8s.restart_deployment(namespace, deployment_name)
        return {"restarted": True, "namespace": namespace, "deployment_name": deployment_name}

    result = await cast(MutationContextLike, ctx.deps.mutation_context).execute(
        action_type="restart_deployment",
        namespace=namespace,
        target=deployment_name,
        payload=payload,
        manifest=None,
        executor=executor,
        severity_override=ActionSeverity.NORMAL,
    )
    return result.message


async def scale_deployment(
    ctx: RunContext[AgentDeps],
    namespace: str,
    deployment_name: str,
    replicas: int,
) -> str:
    """Scale a Deployment to N replicas."""
    if replicas < 0:
        return "scale_deployment failed before action creation: replicas must be >= 0"
    if ctx.deps.mutation_context is None:
        return "scale_deployment unavailable: mutation context is not configured"
    try:
        deployment = await ctx.deps.k8s.get_deployment(namespace, deployment_name)
        namespace_obj = await ctx.deps.k8s.get_namespace(namespace)
    except K8sClientError as exc:
        return f"scale_deployment failed before action creation: {exc}"

    prior_zero = await _has_prior_scale_to_zero(ctx, namespace, deployment_name)
    severity = (
        ActionSeverity.CRITICAL if replicas == 0 and not prior_zero else ActionSeverity.NORMAL
    )
    payload = {
        "namespace": namespace,
        "deployment_name": deployment_name,
        "current_replicas": _deployment_replicas(deployment),
        "target_replicas": replicas,
        "replicas": replicas,
        "prior_scale_to_zero": prior_zero,
        "namespace_labels": {namespace: _labels(namespace_obj)},
    }

    async def executor() -> dict[str, Any]:
        await ctx.deps.k8s.scale_deployment(namespace, deployment_name, replicas)
        return {
            "scaled": True,
            "namespace": namespace,
            "deployment_name": deployment_name,
            "replicas": replicas,
        }

    result = await cast(MutationContextLike, ctx.deps.mutation_context).execute(
        action_type="scale_deployment",
        namespace=namespace,
        target=deployment_name,
        payload=payload,
        manifest=None,
        executor=executor,
        severity_override=severity,
    )
    return result.message


async def delete_pod_persistent(
    ctx: RunContext[AgentDeps],
    namespace: str,
    pod_name: str,
) -> str:
    """Delete a pod permanently. Always requires approval."""
    if ctx.deps.mutation_context is None:
        return "delete_pod_persistent unavailable: mutation context is not configured"
    try:
        pod = await ctx.deps.k8s.get_pod(namespace, pod_name)
        namespace_obj = await ctx.deps.k8s.get_namespace(namespace)
    except K8sClientError as exc:
        return f"delete_pod_persistent failed before action creation: {exc}"

    owner_refs = _owner_references(pod)
    warning = (
        " Warning: pod has an owner and will be recreated by Kubernetes." if owner_refs else ""
    )
    payload: dict[str, Any] = {
        "namespace": namespace,
        "pod_name": pod_name,
        "pod_phase": _pod_phase(pod),
        "container_statuses": _container_statuses(pod),
        "namespace_labels": {namespace: _labels(namespace_obj)},
        "owner_references": owner_refs,
        "warning": warning.strip() or None,
    }

    async def executor() -> dict[str, Any]:
        await ctx.deps.k8s.delete_pod(namespace, pod_name)
        return {
            "deleted": True,
            "namespace": namespace,
            "pod_name": pod_name,
            "will_recreate": bool(owner_refs),
        }

    result = await cast(MutationContextLike, ctx.deps.mutation_context).execute(
        action_type="delete_pod",
        namespace=namespace,
        target=pod_name,
        payload=payload,
        manifest=None,
        executor=executor,
        severity_override=ActionSeverity.NORMAL,
    )
    return f"{result.message}{warning}"


async def apply_manifest(ctx: RunContext[AgentDeps], yaml_text: str) -> str:
    """Apply one Kubernetes manifest YAML in a tenant namespace."""
    if ctx.deps.mutation_context is None:
        return "apply_manifest unavailable: mutation context is not configured"
    try:
        manifest = _parse_single_yaml_manifest(yaml_text)
        kind = _manifest_kind(manifest)
        name = _manifest_name(manifest)
        namespace = _manifest_target_namespace(manifest)
        namespace_labels = await _labels_for_manifest(ctx, manifest, namespace)
    except (K8sClientError, ValueError) as exc:
        return f"apply_manifest failed before action creation: {exc}"

    payload: dict[str, Any] = {
        "kind": kind,
        "name": name,
        "namespace": namespace,
        "namespace_labels": {namespace: namespace_labels},
    }

    async def executor() -> dict[str, Any]:
        return await ctx.deps.k8s.apply_manifest(yaml_text)

    result = await cast(MutationContextLike, ctx.deps.mutation_context).execute(
        action_type="apply_manifest",
        namespace=namespace,
        target=name,
        payload=payload,
        manifest=manifest,
        executor=executor,
        severity_override=ActionSeverity.NORMAL,
    )
    return result.message


async def update_configmap(
    ctx: RunContext[AgentDeps],
    namespace: str,
    name: str,
    data: dict[str, str],
) -> str:
    """Update specific keys in a ConfigMap using merge semantics."""
    if ctx.deps.mutation_context is None:
        return "update_configmap unavailable: mutation context is not configured"
    try:
        namespace_obj = await ctx.deps.k8s.get_namespace(namespace)
    except K8sClientError as exc:
        return f"update_configmap failed before action creation: {exc}"
    payload = {
        "namespace": namespace,
        "name": name,
        "data_keys": sorted(data),
        "namespace_labels": {namespace: _labels(namespace_obj)},
    }

    async def executor() -> dict[str, Any]:
        await ctx.deps.k8s.update_configmap(namespace, name, data)
        return {"updated": True, "namespace": namespace, "name": name, "data_keys": sorted(data)}

    result = await cast(MutationContextLike, ctx.deps.mutation_context).execute(
        action_type="update_configmap",
        namespace=namespace,
        target=name,
        payload=payload,
        manifest=None,
        executor=executor,
        severity_override=ActionSeverity.NORMAL,
    )
    return result.message


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


async def _labels_for_manifest(
    ctx: RunContext[AgentDeps],
    manifest: dict[str, Any],
    namespace: str,
) -> dict[str, str]:
    if _manifest_kind(manifest) == "Namespace":
        metadata = _metadata(manifest)
        labels = metadata.get("labels")
        if isinstance(labels, Mapping):
            return {
                str(key): str(item)
                for key, item in labels.items()
                if isinstance(key, str) and isinstance(item, str)
            }
        return {}
    namespace_obj = await ctx.deps.k8s.get_namespace(namespace)
    return _labels(namespace_obj)


async def _has_prior_scale_to_zero(
    ctx: RunContext[AgentDeps],
    namespace: str,
    deployment_name: str,
) -> bool:
    if ctx.deps.action_repo_factory is None:
        return False
    repo = await ctx.deps.action_repo_factory()
    actions = await repo.list_recent(limit=100)
    for action in actions:
        if action.action_type != "scale_deployment":
            continue
        if action.namespace != namespace or action.target != deployment_name:
            continue
        payload = _payload_dict(action.payload)
        if payload.get("target_replicas") == 0 or payload.get("replicas") == 0:
            return True
    return False


def _payload_dict(value: str) -> dict[str, Any]:
    try:
        import json

        parsed = json.loads(value)
    except ValueError:
        return {}
    return cast(dict[str, Any], parsed) if isinstance(parsed, dict) else {}


def _deployment_replicas(deployment: object) -> int | None:
    spec = _get_attr(deployment, "spec")
    return _int_or_none(_get_attr(spec, "replicas"))


def _deployment_ready_replicas(deployment: object) -> int | None:
    status = _get_attr(deployment, "status")
    return _int_or_none(_get_attr(status, "readyReplicas", "ready_replicas"))


def _deployment_available_replicas(deployment: object) -> int | None:
    status = _get_attr(deployment, "status")
    return _int_or_none(_get_attr(status, "availableReplicas", "available_replicas"))


def _parse_single_yaml_manifest(yaml_text: str) -> dict[str, Any]:
    try:
        documents = list(yaml.safe_load_all(yaml_text))
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML syntax: {exc}") from exc
    documents = [document for document in documents if document is not None]
    if len(documents) != 1:
        raise ValueError("multi-document YAML is not allowed")
    manifest = documents[0]
    if not isinstance(manifest, dict):
        raise ValueError("manifest must be a YAML object")
    return cast(dict[str, Any], manifest)


def _manifest_kind(manifest: dict[str, Any]) -> str:
    kind = manifest.get("kind")
    if not isinstance(kind, str) or not kind:
        raise ValueError("manifest kind is required")
    return kind


def _metadata(manifest: dict[str, Any]) -> dict[str, Any]:
    metadata = manifest.get("metadata")
    if not isinstance(metadata, dict):
        raise ValueError("manifest metadata is required")
    return cast(dict[str, Any], metadata)


def _manifest_name(manifest: dict[str, Any]) -> str:
    name = _metadata(manifest).get("name")
    if not isinstance(name, str) or not name:
        raise ValueError("manifest metadata.name is required")
    return name


def _manifest_target_namespace(manifest: dict[str, Any]) -> str:
    metadata = _metadata(manifest)
    if _manifest_kind(manifest) == "Namespace":
        return _manifest_name(manifest)
    namespace = metadata.get("namespace")
    if not isinstance(namespace, str) or not namespace:
        raise ValueError("manifest metadata.namespace is required")
    return namespace


def _container_statuses(pod: object) -> list[dict[str, Any]]:
    status = _get_attr(pod, "status")
    statuses = _sequence_attr(status, "containerStatuses", "container_statuses")
    return [_container_status(status) for status in statuses]


def _container_status(status: object) -> dict[str, Any]:
    return {
        "name": _str_or_empty(_get_attr(status, "name")),
        "ready": bool(_get_attr(status, "ready")),
        "restart_count": _int_or_zero(_get_attr(status, "restartCount", "restart_count")),
        "reason": _state_reason(status),
    }


def _state_reason(status: object) -> str | None:
    for state_holder_name in ("state", "lastState", "last_state"):
        state_holder = _get_attr(status, state_holder_name)
        for state_name in ("waiting", "terminated", "running"):
            state = _get_attr(state_holder, state_name)
            reason = _str_or_none(_get_attr(state, "reason"))
            if reason is not None:
                return reason
    return None


def _owner_references(pod: object) -> list[dict[str, str]]:
    metadata = _get_attr(pod, "metadata")
    refs = _sequence_attr(metadata, "ownerReferences", "owner_references")
    result: list[dict[str, str]] = []
    for ref in refs:
        name = _str_or_none(_get_attr(ref, "name"))
        kind = _str_or_none(_get_attr(ref, "kind"))
        if name is not None and kind is not None:
            result.append({"kind": kind, "name": name})
    return result


def _pod_phase(pod: object) -> str | None:
    status = _get_attr(pod, "status")
    return _str_or_none(_get_attr(status, "phase"))


def _get_attr(obj: object | None, *names: str) -> object | None:
    if obj is None:
        return None
    for name in names:
        if isinstance(obj, Mapping) and name in obj:
            return cast(object, obj[name])
        value = getattr(obj, name, None)
        if value is not None:
            return cast(object, value)
    return None


def _sequence_attr(obj: object | None, *names: str) -> Sequence[object]:
    value = _get_attr(obj, *names)
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return value
    return []


def _str_or_none(value: object | None) -> str | None:
    return value if isinstance(value, str) else None


def _str_or_empty(value: object | None) -> str:
    return value if isinstance(value, str) else ""


def _int_or_none(value: object | None) -> int | None:
    return value if isinstance(value, int) else None


def _int_or_zero(value: object | None) -> int:
    return value if isinstance(value, int) else 0

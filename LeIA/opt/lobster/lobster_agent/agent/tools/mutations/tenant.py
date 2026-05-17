import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, Protocol, cast

import yaml
from pydantic_ai import RunContext

from lobster_agent.agent.deps import AgentDeps
from lobster_agent.agent.mutations import ActionResult
from lobster_agent.agent.mutations.manifests import ManifestRenderer
from lobster_agent.clients.k8s import K8sClientError
from lobster_agent.domain import policy
from lobster_agent.domain.severity import ActionSeverity
from lobster_agent.domain.tenants import TIER_LIMITS, TenantTier, TenantType

DNS_1123_LABEL = re.compile(r"^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$")


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


async def deploy_tenant(
    ctx: RunContext[AgentDeps],
    tenant_type: TenantType,
    name: str,
    tier: TenantTier = TenantTier.FREE,
    hostname: str | None = None,
    image: str | None = None,
    port: int = 80,
    env: dict[str, str] | None = None,
    owner: str | None = None,
    admin_email: str | None = None,
) -> str:
    """Deploy a new tenant. CRITICAL severity always.

    Args:
        tenant_type: One of "static_site" (HTML), "wordpress", or "web_app"
            (custom Docker image — requires `image`).
        name: DNS-1123 label used as the namespace; must match
            `[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?`.
        tier: "free" (default), "basic" or "premium".
        hostname: Public hostname; defaults to `<name>.saasphere.local`.
        image: Container image, required for `web_app`.
        admin_email: Required for `wordpress`.
    """
    if ctx.deps.mutation_context is None:
        return "deploy_tenant unavailable: mutation context is not configured"
    if not DNS_1123_LABEL.match(name):
        return "deploy_tenant failed before action creation: name must be a DNS-1123 label"
    try:
        parsed_type = TenantType(tenant_type)
        parsed_tier = TenantTier(tier)
    except ValueError as exc:
        return f"deploy_tenant failed before action creation: {exc}"
    if parsed_type == TenantType.WEB_APP and not image:
        return "deploy_tenant failed before action creation: web_app requires image"
    if parsed_type == TenantType.WORDPRESS and not admin_email:
        return "deploy_tenant failed before action creation: wordpress requires admin_email"

    hostname = hostname or f"{name}.saasphere.local"
    context: dict[str, Any] = {
        "name": name,
        "tier": parsed_tier.value,
        "limits": TIER_LIMITS[parsed_tier],
        "hostname": hostname,
        "image": image,
        "port": port,
        "env": env or {},
        "owner": owner or "admin",
        "admin_email": admin_email,
    }
    try:
        resources = ManifestRenderer().render(parsed_type, context)
    except Exception as exc:
        return f"deploy_tenant failed before action creation: {exc}"

    for resource in resources:
        resource_namespace = _resource_namespace(resource, default=name)
        decision = policy.validate(
            "apply_manifest",
            resource_namespace,
            manifest=resource,
            context={
                "namespace_labels": {name: _namespace_labels(resources, name)},
                "internal_tooling": True,
            },
        )
        if not decision.allowed:
            return f"deploy_tenant rejected by policy: {decision.reason}"

    payload: dict[str, Any] = {
        "tenant_type": parsed_type.value,
        "name": name,
        "tier": parsed_tier.value,
        "hostname": hostname,
        "owner": owner or "admin",
        "resource_count": len(resources),
        "namespace_labels": {name: _namespace_labels(resources, name)},
    }

    async def executor() -> dict[str, Any]:
        try:
            applied: list[dict[str, str]] = []
            for resource in _dependency_order(resources):
                applied.append(await ctx.deps.k8s.apply_manifest(yaml.safe_dump(resource)))
            host_path: str | None = None
            host_node: str | None = None
            pv_name: str | None = None
            if parsed_type == TenantType.STATIC_SITE:
                pvc_name = f"{name}-html"
                bound = await ctx.deps.k8s.wait_for_pvc_bound(name, pvc_name, timeout_seconds=120)
                if not bound:
                    raise K8sClientError(
                        f"PVC {name}/{pvc_name} did not bind within 120s; "
                        "check the local-path provisioner and that the deployment pod scheduled"
                    )
                storage = await ctx.deps.k8s.get_pvc_storage_path(name, pvc_name)
                host_path = storage.get("path")
                host_node = storage.get("node")
                pv_name = storage.get("pv_name")
            return {
                "applied": applied,
                "url": f"https://{hostname}",
                "host_path": host_path,
                "host_node": host_node,
                "pv_name": pv_name,
            }
        except Exception:
            await ctx.deps.k8s.delete_namespace(name)
            raise

    result = await cast(MutationContextLike, ctx.deps.mutation_context).execute(
        action_type="deploy_tenant",
        namespace=name,
        target=name,
        payload=payload,
        manifest=None,
        executor=executor,
        severity_override=ActionSeverity.CRITICAL,
    )
    if result.status.value != "completed":
        return result.message
    return _deploy_message(parsed_type, hostname, name, result.data)


async def delete_tenant(
    ctx: RunContext[AgentDeps],
    namespace: str,
    confirm_namespace: str,
) -> str:
    """Delete an entire tenant including all its resources. CRITICAL."""
    if confirm_namespace != namespace:
        return "delete_tenant refused: confirm_namespace must exactly match namespace"
    if ctx.deps.mutation_context is None:
        return "delete_tenant unavailable: mutation context is not configured"
    try:
        labels = _labels(await ctx.deps.k8s.get_namespace(namespace))
    except K8sClientError as exc:
        return f"delete_tenant failed before action creation: {exc}"
    if labels.get("saasphere.io/tenant") != "true":
        return "delete_tenant refused: namespace is not a tenant"

    async def executor() -> dict[str, Any]:
        await ctx.deps.k8s.delete_namespace(namespace)
        return {"deleted": True, "namespace": namespace}

    result = await cast(MutationContextLike, ctx.deps.mutation_context).execute(
        "delete_tenant",
        namespace,
        namespace,
        {"namespace": namespace, "namespace_labels": {namespace: labels}},
        None,
        executor,
        severity_override=ActionSeverity.CRITICAL,
    )
    return result.message


async def pause_tenant(ctx: RunContext[AgentDeps], namespace: str) -> str:
    """Scale all deployments in the tenant to 0 replicas."""
    if ctx.deps.mutation_context is None:
        return "pause_tenant unavailable: mutation context is not configured"
    try:
        labels = _labels(await ctx.deps.k8s.get_namespace(namespace))
        deployments = await ctx.deps.k8s.list_deployments(namespace)
    except K8sClientError as exc:
        return f"pause_tenant failed before action creation: {exc}"
    replica_map = {_metadata_name(item): _deployment_replicas(item) or 0 for item in deployments}

    async def executor() -> dict[str, Any]:
        annotations = {
            f"saasphere.io/paused-replicas-{name}": str(replicas)
            for name, replicas in replica_map.items()
        }
        await ctx.deps.k8s.patch_namespace_annotations(namespace, annotations)
        for deployment, replicas in replica_map.items():
            _ = replicas
            await ctx.deps.k8s.scale_deployment(namespace, deployment, 0)
        return {"paused": True, "replicas": replica_map}

    result = await cast(MutationContextLike, ctx.deps.mutation_context).execute(
        "pause_tenant",
        namespace,
        namespace,
        {"namespace": namespace, "replicas": replica_map, "namespace_labels": {namespace: labels}},
        None,
        executor,
        severity_override=ActionSeverity.NORMAL,
    )
    return result.message


async def resume_tenant(ctx: RunContext[AgentDeps], namespace: str) -> str:
    """Restore replicas from pause annotations."""
    if ctx.deps.mutation_context is None:
        return "resume_tenant unavailable: mutation context is not configured"
    try:
        labels = _labels(await ctx.deps.k8s.get_namespace(namespace))
        annotations = await ctx.deps.k8s.get_namespace_annotations(namespace)
    except K8sClientError as exc:
        return f"resume_tenant failed before action creation: {exc}"
    prefix = "saasphere.io/paused-replicas-"
    replicas = {
        key.removeprefix(prefix): int(value)
        for key, value in annotations.items()
        if key.startswith(prefix) and value.isdigit()
    }
    if not replicas:
        return "resume_tenant failed before action creation: tenant was not paused"

    async def executor() -> dict[str, Any]:
        for deployment, count in replicas.items():
            await ctx.deps.k8s.scale_deployment(namespace, deployment, count)
        return {"resumed": True, "replicas": replicas}

    result = await cast(MutationContextLike, ctx.deps.mutation_context).execute(
        "resume_tenant",
        namespace,
        namespace,
        {"namespace": namespace, "replicas": replicas, "namespace_labels": {namespace: labels}},
        None,
        executor,
        severity_override=ActionSeverity.AUTONOMOUS,
    )
    return result.message


async def verify_tenant_health(ctx: RunContext[AgentDeps], namespace: str) -> str:
    """Read-only composite health check."""
    if ctx.deps.mutation_context is None:
        return "verify_tenant_health unavailable: mutation context is not configured"
    try:
        labels = _labels(await ctx.deps.k8s.get_namespace(namespace))
    except K8sClientError as exc:
        return f"verify_tenant_health failed before action creation: {exc}"

    async def executor() -> dict[str, Any]:
        deployments = await ctx.deps.k8s.list_deployments(namespace)
        pods = await ctx.deps.k8s.list_pods(namespace)
        ingresses = await ctx.deps.k8s.list_ingresses(namespace)
        pvcs = await ctx.deps.k8s.list_pvcs(namespace)
        unhealthy = [
            _metadata_name(dep)
            for dep in deployments
            if (_deployment_replicas(dep) or 0) != (_deployment_ready_replicas(dep) or 0)
        ]
        crashloops = [
            _metadata_name(pod)
            for pod in pods
            if any(
                status.get("reason") == "CrashLoopBackOff" for status in _container_statuses(pod)
            )
        ]
        unbound = [_metadata_name(pvc) for pvc in pvcs if _pvc_phase(pvc) != "Bound"]
        ingress_info = [_health_ingress_info(ingress) for ingress in ingresses]
        warnings = []
        if not ingress_info:
            warnings.append("no ingress configured")
        return {
            "ok": not unhealthy and not crashloops and not warnings and not unbound,
            "unhealthy_deployments": unhealthy,
            "crashloop_pods": crashloops,
            "ingresses": ingress_info,
            "unbound_pvcs": unbound,
            "warnings": warnings,
        }

    result = await cast(MutationContextLike, ctx.deps.mutation_context).execute(
        "verify_tenant_health",
        namespace,
        namespace,
        {"namespace": namespace, "namespace_labels": {namespace: labels}},
        None,
        executor,
        severity_override=ActionSeverity.AUTONOMOUS,
    )
    data = result.data or {}
    if data.get("ok"):
        return f"ok: tenant {namespace} healthy; ingresses={data.get('ingresses', [])}"
    return f"warning: tenant {namespace} health issues: {data}"


def _deploy_message(
    tenant_type: TenantType,
    hostname: str,
    name: str,
    data: dict[str, Any] | None,
) -> str:
    url = f"https://{hostname}"
    if tenant_type == TenantType.STATIC_SITE:
        payload = data or {}
        host_path = payload.get("host_path")
        host_node = payload.get("host_node")
        if host_path and host_node:
            target = f"scp target: {host_node}:{host_path}"
        elif host_path:
            target = f"scp target: <node>:{host_path}"
        else:
            target = (
                f"kubectl cp ./index.html {name}/$(kubectl get pod -n {name} "
                f"-l app={name} -o jsonpath='{{.items[0].metadata.name}}'):"
                "/usr/share/nginx/html/index.html"
            )
        return f"tenant deployed: {url}; mount: /usr/share/nginx/html; {target}"
    if tenant_type == TenantType.WORDPRESS:
        return f"tenant deployed: {url}; admin: {url}/wp-admin"
    return f"tenant deployed: {url}; namespace: {name}"


def _dependency_order(resources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    order = {
        "Namespace": 0,
        "Secret": 1,
        "PersistentVolumeClaim": 2,
        "ResourceQuota": 3,
        "Deployment": 4,
        "Service": 5,
        "Ingress": 6,
    }
    return sorted(resources, key=lambda item: order.get(str(item.get("kind")), 99))


def _namespace_labels(resources: list[dict[str, Any]], name: str) -> dict[str, str]:
    for resource in resources:
        if resource.get("kind") == "Namespace" and _metadata_name(resource) == name:
            labels = _get_attr(_get_attr(resource, "metadata"), "labels")
            if isinstance(labels, Mapping):
                return {str(key): str(value) for key, value in labels.items()}
    return {}


def _resource_namespace(resource: dict[str, Any], default: str) -> str:
    if resource.get("kind") == "Namespace":
        return _metadata_name(resource)
    namespace = _get_attr(_get_attr(resource, "metadata"), "namespace")
    return namespace if isinstance(namespace, str) else default


def _labels(namespace_obj: object) -> dict[str, str]:
    labels = _get_attr(_get_attr(namespace_obj, "metadata"), "labels")
    if not isinstance(labels, Mapping):
        return {}
    return {str(key): str(value) for key, value in labels.items()}


def _metadata_name(obj: object) -> str:
    value = _get_attr(_get_attr(obj, "metadata"), "name")
    return value if isinstance(value, str) else ""


def _deployment_replicas(deployment: object) -> int | None:
    value = _get_attr(_get_attr(deployment, "spec"), "replicas")
    return value if isinstance(value, int) else None


def _deployment_ready_replicas(deployment: object) -> int | None:
    value = _get_attr(_get_attr(deployment, "status"), "readyReplicas", "ready_replicas")
    return value if isinstance(value, int) else None


def _pvc_phase(pvc: object) -> str | None:
    value = _get_attr(_get_attr(pvc, "status"), "phase")
    return value if isinstance(value, str) else None


def _container_statuses(pod: object) -> list[dict[str, Any]]:
    statuses = _sequence_attr(_get_attr(pod, "status"), "containerStatuses", "container_statuses")
    return [{"reason": _state_reason(status)} for status in statuses]


def _health_ingress_info(ingress: object) -> dict[str, Any]:
    hosts_value = _get_attr(ingress, "hosts")
    hosts = (
        [str(host) for host in hosts_value if isinstance(host, str)]
        if isinstance(hosts_value, list)
        else []
    )
    address = _get_attr(ingress, "address")
    metadata = _get_attr(ingress, "metadata")
    name = _get_attr(ingress, "name") or _get_attr(metadata, "name")
    return {
        "name": _str_or_empty(name),
        "hostname": hosts[0] if hosts else None,
        "hosts": hosts,
        "address": address if isinstance(address, str) else None,
        "address_assigned": isinstance(address, str) and bool(address),
    }


def _state_reason(status: object) -> str | None:
    for holder_name in ("state", "lastState", "last_state"):
        holder = _get_attr(status, holder_name)
        for state_name in ("waiting", "terminated", "running"):
            reason = _get_attr(_get_attr(holder, state_name), "reason")
            if isinstance(reason, str):
                return reason
    return None


def _str_or_empty(value: object | None) -> str:
    return value if isinstance(value, str) else ""


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

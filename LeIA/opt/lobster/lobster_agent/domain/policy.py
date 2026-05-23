from dataclasses import dataclass, field
from typing import Any

from lobster_agent.domain.severity import ActionSeverity

SYSTEM_NAMESPACES = {"kube-system", "kube-public", "metallb-system", "saasphere-system"}
TENANT_NAMESPACE_PREFIX = "tenant-"
TENANT_LABEL = "saasphere.io/tenant"
PROTECTED_RESOURCE_NAMES = ("traefik", "coredns", "metrics-server")
FORBIDDEN_MANIFEST_KINDS = {
    "Secret",
    "ServiceAccount",
    "Role",
    "RoleBinding",
    "ClusterRole",
    "ClusterRoleBinding",
    "Pod",
}
READ_ONLY_ACTIONS = {
    "get_pod",
    "list_pods",
    "list_deployments",
    "list_namespaces",
    "list_recent_events",
    "query_prometheus",
    "query_loki",
}
ACTION_SEVERITIES = {
    "restart_pod": ActionSeverity.NORMAL,
    "restart_deployment": ActionSeverity.NORMAL,
    "delete_pod": ActionSeverity.NORMAL,
    "update_configmap": ActionSeverity.NORMAL,
    "apply_manifest": ActionSeverity.NORMAL,
    "scale_deployment": ActionSeverity.NORMAL,
    "deploy_tenant": ActionSeverity.CRITICAL,
    "delete_tenant": ActionSeverity.CRITICAL,
    "pause_tenant": ActionSeverity.NORMAL,
    "resume_tenant": ActionSeverity.AUTONOMOUS,
    "verify_tenant_health": ActionSeverity.AUTONOMOUS,
    "scale_tenant": ActionSeverity.NORMAL,
    "annotate_resource": ActionSeverity.AUTONOMOUS,
    "pin_deployment_to_node": ActionSeverity.AUTONOMOUS,
    "unpin_deployment_from_node": ActionSeverity.AUTONOMOUS,
    "cordon_node": ActionSeverity.NORMAL,
    "uncordon_node": ActionSeverity.AUTONOMOUS,
}


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    severity: ActionSeverity
    reason: str
    violations: list[str] = field(default_factory=list)


def validate(
    action_type: str,
    namespace: str,
    manifest: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
    action_repo: Any | None = None,
) -> PolicyDecision:
    _ = action_repo
    context = context or {}
    if namespace in SYSTEM_NAMESPACES:
        return PolicyDecision(
            allowed=False,
            severity=ActionSeverity.FORBIDDEN,
            reason="namespace is hard-blocked",
            violations=["namespace_hard_block"],
        )

    if action_type not in ACTION_SEVERITIES and action_type not in READ_ONLY_ACTIONS:
        return PolicyDecision(
            allowed=False,
            severity=ActionSeverity.FORBIDDEN,
            reason="unknown action",
            violations=["unknown_action"],
        )

    violations: list[str] = []
    if namespace in SYSTEM_NAMESPACES and action_type not in READ_ONLY_ACTIONS:
        violations.append("system_namespace")
    if _targets_protected_resource(action_type, namespace, manifest, context):
        violations.append("protected_resource")
    if manifest is not None:
        violations.extend(_manifest_violations(manifest, context))

    if violations:
        return PolicyDecision(
            allowed=False,
            severity=ActionSeverity.FORBIDDEN,
            reason=_reason_for_violations(violations),
            violations=violations,
        )

    if action_type in READ_ONLY_ACTIONS:
        return PolicyDecision(
            allowed=True,
            severity=ActionSeverity.AUTONOMOUS,
            reason="read-only action",
            violations=[],
        )

    if not _is_tenant_namespace(namespace, context):
        return PolicyDecision(
            allowed=False,
            severity=ActionSeverity.FORBIDDEN,
            reason="namespace is not tenant-whitelisted",
            violations=["tenant_whitelist"],
        )

    severity = ACTION_SEVERITIES[action_type]
    if action_type == "scale_deployment":
        severity = _scale_deployment_severity(context)

    return PolicyDecision(
        allowed=True,
        severity=severity,
        reason="allowed by policy",
        violations=[],
    )


def _is_tenant_namespace(namespace: str, context: dict[str, Any]) -> bool:
    labels = context.get("labels")
    if isinstance(labels, dict) and labels.get(TENANT_LABEL) == "true":
        return True

    namespace_labels = context.get("namespace_labels")
    if isinstance(namespace_labels, dict):
        direct = namespace_labels.get(namespace)
        if isinstance(direct, dict) and direct.get(TENANT_LABEL) == "true":
            return True

    tenant_namespaces = context.get("tenant_namespaces")
    return isinstance(tenant_namespaces, (set, list, tuple)) and namespace in tenant_namespaces


def _targets_protected_resource(
    action_type: str,
    namespace: str,
    manifest: dict[str, Any] | None,
    context: dict[str, Any],
) -> bool:
    haystack: list[str] = [action_type, namespace]
    for key in ("target", "name", "resource_name", "deployment", "pod"):
        value = context.get(key)
        if isinstance(value, str):
            haystack.append(value)
    if manifest is not None:
        metadata = manifest.get("metadata")
        if isinstance(metadata, dict):
            for key in ("name", "namespace"):
                value = metadata.get(key)
                if isinstance(value, str):
                    haystack.append(value)
            labels = metadata.get("labels")
            if isinstance(labels, dict):
                haystack.extend(str(value) for value in labels.values())
    lowered = " ".join(haystack).casefold()
    return any(name in lowered for name in PROTECTED_RESOURCE_NAMES)


def _manifest_violations(manifest: dict[str, Any], context: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    kind = manifest.get("kind")
    if (
        isinstance(kind, str)
        and kind in FORBIDDEN_MANIFEST_KINDS
        and not (kind == "Secret" and context.get("internal_tooling") is True)
    ):
        violations.append("forbidden_kind")
    if _contains_key_value(manifest, "privileged", True):
        violations.append("privileged")
    if _has_forbidden_host_path(manifest):
        violations.append("host_path")
    if _contains_key_value(manifest, "hostNetwork", True):
        violations.append("host_network")
    if _contains_key_value(manifest, "hostPID", True):
        violations.append("host_pid")
    if _contains_key_value(manifest, "hostIPC", True):
        violations.append("host_ipc")
    if context.get("enforce_resource_limits", True) and not _has_container_limits(manifest):
        violations.append("missing_resource_limits")
    return violations


def _contains_key_value(value: object, key: str, expected: object) -> bool:
    if isinstance(value, dict):
        return (key in value and value[key] == expected) or any(
            _contains_key_value(child, key, expected) for child in value.values()
        )
    if isinstance(value, list):
        return any(_contains_key_value(child, key, expected) for child in value)
    return False


def _contains_key(value: object, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(_contains_key(child, key) for child in value.values())
    if isinstance(value, list):
        return any(_contains_key(child, key) for child in value)
    return False


_ALLOWED_HOST_PATHS = ("/srv/lobster/static/",)


def _has_forbidden_host_path(value: object) -> bool:
    if isinstance(value, dict):
        if "hostPath" in value:
            hp = value["hostPath"]
            if isinstance(hp, dict):
                path = hp.get("path", "")
                if isinstance(path, str) and any(path.startswith(p) for p in _ALLOWED_HOST_PATHS):
                    return False
            return True
        return any(_has_forbidden_host_path(child) for child in value.values())
    if isinstance(value, list):
        return any(_has_forbidden_host_path(child) for child in value)
    return False


def _has_container_limits(manifest: dict[str, Any]) -> bool:
    containers = _find_containers(manifest)
    if not containers:
        return True
    for container in containers:
        resources = container.get("resources")
        if not isinstance(resources, dict):
            return False
        limits = resources.get("limits")
        if not isinstance(limits, dict):
            return False
        if not limits.get("cpu") or not limits.get("memory"):
            return False
    return True


def _find_containers(value: object) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        containers = value.get("containers")
        if isinstance(containers, list):
            found.extend(item for item in containers if isinstance(item, dict))
        init_containers = value.get("initContainers")
        if isinstance(init_containers, list):
            found.extend(item for item in init_containers if isinstance(item, dict))
        for child in value.values():
            found.extend(_find_containers(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_find_containers(child))
    return found


def _reason_for_violations(violations: list[str]) -> str:
    if "system_namespace" in violations:
        return "system namespace is protected"
    if "protected_resource" in violations:
        return "protected platform resource is targeted"
    if "forbidden_kind" in violations:
        return "manifest kind is forbidden"
    if "privileged" in violations:
        return "privileged manifests are forbidden"
    if "host_path" in violations:
        return "hostPath volumes are forbidden"
    if "host_network" in violations:
        return "hostNetwork is forbidden"
    if "host_pid" in violations:
        return "hostPID is forbidden"
    if "host_ipc" in violations:
        return "hostIPC is forbidden"
    if "missing_resource_limits" in violations:
        return "manifest is missing cpu and memory resource limits"
    return "policy violation"


def _scale_deployment_severity(context: dict[str, Any]) -> ActionSeverity:
    replicas = context.get("replicas", context.get("target_replicas"))
    if replicas == 0 and not bool(context.get("prior_scale_to_zero")):
        return ActionSeverity.CRITICAL
    return ActionSeverity.NORMAL

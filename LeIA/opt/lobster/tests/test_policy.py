from lobster_agent.domain import policy
from lobster_agent.domain.severity import ActionSeverity

TENANT_CONTEXT = {"namespace_labels": {"tenant-x": {"saasphere.io/tenant": "true"}}}


def test_system_namespace_forbidden() -> None:
    decision = policy.validate("restart_pod", "kube-system")

    assert decision.allowed is False
    assert decision.severity == ActionSeverity.FORBIDDEN
    assert "hard-blocked" in decision.reason


def test_kube_system_forbidden_for_any_action_type() -> None:
    decision = policy.validate("unknown", "kube-system")

    assert decision.allowed is False
    assert decision.severity == ActionSeverity.FORBIDDEN
    assert decision.violations == ["namespace_hard_block"]


def test_tenant_label_allows_known_action() -> None:
    decision = policy.validate("restart_pod", "tenant-x", context=TENANT_CONTEXT)

    assert decision.allowed is True
    assert decision.severity == ActionSeverity.NORMAL


def test_non_prefixed_tenant_label_allows_known_action() -> None:
    decision = policy.validate(
        "restart_pod",
        "demo-tfg",
        context={"namespace_labels": {"demo-tfg": {"saasphere.io/tenant": "true"}}},
    )

    assert decision.allowed is True
    assert decision.severity == ActionSeverity.NORMAL


def test_non_prefixed_namespace_without_label_fails_tenant_whitelist() -> None:
    decision = policy.validate("restart_pod", "demo-tfg")

    assert decision.allowed is False
    assert decision.reason == "namespace is not tenant-whitelisted"
    assert decision.violations == ["tenant_whitelist"]


def test_privileged_manifest_forbidden() -> None:
    decision = policy.validate(
        "apply_manifest",
        "tenant-x",
        manifest={
            "spec": {
                "containers": [
                    {
                        "name": "app",
                        "securityContext": {"privileged": True},
                        "resources": {"limits": {"cpu": "100m", "memory": "128Mi"}},
                    }
                ]
            }
        },
        context=TENANT_CONTEXT,
    )

    assert decision.allowed is False
    assert "privileged" in decision.violations


def test_host_path_manifest_forbidden() -> None:
    decision = policy.validate(
        "apply_manifest",
        "tenant-x",
        manifest={
            "spec": {
                "volumes": [{"name": "host", "hostPath": {"path": "/var/run/docker.sock"}}],
                "containers": [
                    {
                        "name": "app",
                        "resources": {"limits": {"cpu": "100m", "memory": "128Mi"}},
                    }
                ],
            }
        },
        context=TENANT_CONTEXT,
    )

    assert decision.allowed is False
    assert "host_path" in decision.violations


def test_manifest_without_limits_forbidden_when_enforced() -> None:
    decision = policy.validate(
        "apply_manifest",
        "tenant-x",
        manifest={"spec": {"containers": [{"name": "app"}]}},
        context={**TENANT_CONTEXT, "enforce_resource_limits": True},
    )

    assert decision.allowed is False
    assert "missing_resource_limits" in decision.violations


def test_unknown_action_forbidden() -> None:
    decision = policy.validate("unknown", "tenant-x", context=TENANT_CONTEXT)

    assert decision.allowed is False
    assert decision.reason == "unknown action"


def test_scale_deployment_zero_first_time_is_critical() -> None:
    decision = policy.validate(
        "scale_deployment",
        "tenant-x",
        context={**TENANT_CONTEXT, "replicas": 0, "prior_scale_to_zero": False},
    )

    assert decision.allowed is True
    assert decision.severity == ActionSeverity.CRITICAL


def test_apply_manifest_privileged_reason() -> None:
    decision = policy.validate(
        "apply_manifest",
        "tenant-x",
        manifest={
            "kind": "Deployment",
            "spec": {
                "containers": [
                    {
                        "name": "app",
                        "securityContext": {"privileged": True},
                        "resources": {"limits": {"cpu": "100m", "memory": "128Mi"}},
                    }
                ]
            },
        },
        context=TENANT_CONTEXT,
    )

    assert decision.allowed is False
    assert "privileged" in decision.reason


def test_apply_manifest_secret_kind_forbidden_reason() -> None:
    decision = policy.validate(
        "apply_manifest",
        "tenant-x",
        manifest={"kind": "Secret", "metadata": {"name": "s", "namespace": "tenant-x"}},
        context=TENANT_CONTEXT,
    )

    assert decision.allowed is False
    assert "forbidden" in decision.reason

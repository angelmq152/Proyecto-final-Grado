from datetime import UTC, datetime

from lobster_agent.domain.models import (
    AlertInfo,
    GlobalHealth,
    LogEntryPublic,
    NodeMetrics,
    TenantMetrics,
)


def test_domain_models_instantiate_and_serialize() -> None:
    now = datetime(2026, 5, 11, 10, 30, tzinfo=UTC)
    log = LogEntryPublic(timestamp=now, labels={"service": "lobster"}, line="ok")
    node = NodeMetrics(node="matrix", cpu_pct=12.5, memory_pct=44.0)
    tenant = TenantMetrics(namespace="tenant-a")
    health = GlobalHealth(timestamp=now, nodes=[node], total_tenants=None)
    alert = AlertInfo(name="HighCPU", severity="warning")

    assert log.model_dump()["labels"] == {"service": "lobster"}
    assert node.model_dump()["disk_pct"] is None
    assert tenant.model_dump()["namespace"] == "tenant-a"
    assert health.model_dump()["nodes"][0]["node"] == "matrix"
    assert alert.model_dump()["labels"] == {}


def test_alert_info_uses_independent_default_dicts() -> None:
    first = AlertInfo(name="A", severity="warning")
    second = AlertInfo(name="B", severity="critical")

    first.labels["tenant"] = "one"

    assert second.labels == {}

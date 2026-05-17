from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from lobster_agent.agent.tools.k8s_read import (
    get_events,
    get_tenant,
    list_deployments,
    list_pods,
    list_tenants,
)
from lobster_agent.domain.models import ContainerStatus, PodInfo


class FakeK8sClient:
    def __init__(
        self,
        namespaces: list[object] | None = None,
        pods: list[object] | None = None,
        deployments: list[object] | None = None,
        events: list[object] | None = None,
    ) -> None:
        self.namespaces = namespaces or []
        self.pods = pods or []
        self.deployments = deployments or []
        self.events = events or []
        self.label_selectors: list[str | None] = []

    async def list_namespaces(self, label_selector: str | None = None) -> list[object]:
        self.label_selectors.append(label_selector)
        return self.namespaces

    async def get_namespace(self, name: str) -> object:
        for namespace in self.namespaces:
            if namespace.metadata.name == name:
                return namespace
        raise KeyError(name)

    async def list_pods(self, namespace: str) -> list[object]:
        return self.pods

    async def list_deployments(self, namespace: str) -> list[object]:
        return self.deployments

    async def list_events(self, namespace: str) -> list[object]:
        return self.events


def namespace(
    name: str,
    labels: dict[str, str] | None = None,
    annotations: dict[str, str] | None = None,
) -> object:
    return SimpleNamespace(
        metadata=SimpleNamespace(
            name=name,
            namespace=None,
            labels=labels or {},
            annotations=annotations or {},
        )
    )


async def test_list_tenants_uses_base_label_selector() -> None:
    client = FakeK8sClient([namespace("tenant-a")])

    result = await list_tenants(client)

    assert client.label_selectors == ["saasphere.io/tenant=true"]
    assert result[0].namespace == "tenant-a"


async def test_list_tenants_adds_tier_and_type_to_selector() -> None:
    client = FakeK8sClient()

    await list_tenants(client, tier="premium", type="wordpress")

    assert client.label_selectors == [
        "saasphere.io/tenant=true,saasphere.io/tier=premium,saasphere.io/type=wordpress"
    ]


async def test_list_tenants_converts_labels_and_annotations() -> None:
    last_active = "2026-05-11T10:00:00+00:00"
    client = FakeK8sClient(
        [
            namespace(
                "tenant-a",
                labels={
                    "saasphere.io/tier": "premium",
                    "saasphere.io/type": "nextcloud",
                    "saasphere.io/scaled-to-zero": "true",
                },
                annotations={
                    "saasphere.io/owner": "angel",
                    "saasphere.io/last-active": last_active,
                },
            )
        ]
    )

    result = await list_tenants(client)

    assert result[0].tier == "premium"
    assert result[0].type == "nextcloud"
    assert result[0].owner == "angel"
    assert result[0].last_active == datetime.fromisoformat(last_active)
    assert result[0].is_scaled_to_zero is True


async def test_get_tenant_converts_namespace() -> None:
    client = FakeK8sClient([namespace("tenant-a", labels={"saasphere.io/tier": "free"})])

    result = await get_tenant(client, "tenant-a")

    assert result.namespace == "tenant-a"
    assert result.tier == "free"


async def test_list_pods_converts_pods_to_pod_info() -> None:
    created_at = datetime.now(UTC) - timedelta(seconds=30)
    pod = SimpleNamespace(
        metadata=SimpleNamespace(name="web-1", namespace="tenant-a", creationTimestamp=created_at),
        spec=SimpleNamespace(nodeName="matrix"),
        status=SimpleNamespace(
            phase="Running",
            containerStatuses=[
                SimpleNamespace(
                    name="web",
                    ready=True,
                    restartCount=2,
                    lastState=SimpleNamespace(terminated=SimpleNamespace(reason="OOMKilled")),
                ),
                SimpleNamespace(name="sidecar", ready=True, restartCount=1, lastState=None),
            ],
        ),
    )
    client = FakeK8sClient(pods=[pod])

    result = await list_pods(client, "tenant-a")

    assert result == [
        PodInfo(
            namespace="tenant-a",
            name="web-1",
            phase="Running",
            ready=True,
            restart_count=3,
            container_statuses=result[0].container_statuses,
            age_seconds=result[0].age_seconds,
            node="matrix",
        )
    ]
    assert result[0].container_statuses[0].last_state_reason == "OOMKilled"


async def test_list_deployments_converts_deployments() -> None:
    deployment = SimpleNamespace(
        metadata=SimpleNamespace(name="web", namespace="tenant-a"),
        spec=SimpleNamespace(replicas=3),
        status=SimpleNamespace(availableReplicas=2, readyReplicas=2),
    )
    client = FakeK8sClient(deployments=[deployment])

    result = await list_deployments(client, "tenant-a")

    assert result[0].namespace == "tenant-a"
    assert result[0].name == "web"
    assert result[0].replicas == 3
    assert result[0].available_replicas == 2
    assert result[0].ready_replicas == 2


async def test_get_events_converts_events() -> None:
    timestamp = datetime(2026, 5, 11, 10, 0, tzinfo=UTC)
    event = SimpleNamespace(
        metadata=SimpleNamespace(namespace="tenant-a"),
        involvedObject=SimpleNamespace(kind="Pod", name="web-1"),
        eventTime=timestamp,
        reason="BackOff",
        message="Back-off restarting failed container",
        type="Warning",
    )
    client = FakeK8sClient(events=[event])

    result = await get_events(client, "tenant-a")

    assert result[0].timestamp == timestamp
    assert result[0].namespace == "tenant-a"
    assert result[0].kind == "Pod"
    assert result[0].name == "web-1"
    assert result[0].reason == "BackOff"
    assert result[0].type == "Warning"


def test_pod_info_default_container_statuses_are_not_shared() -> None:
    first = PodInfo(namespace="a", name="pod-a")
    second = PodInfo(namespace="b", name="pod-b")

    first.container_statuses.append(ContainerStatus(name="bad", ready=False, restart_count=0))

    assert second.container_statuses == []

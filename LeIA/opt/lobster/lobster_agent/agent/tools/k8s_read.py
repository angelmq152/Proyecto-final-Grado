from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Literal, Protocol, TypeVar, cast

from lobster_agent.domain.models import (
    ContainerStatus,
    DeploymentInfo,
    IngressInfo,
    K8sEvent,
    PodInfo,
    Tenant,
)

T = TypeVar("T")


class K8sReader(Protocol):
    async def list_namespaces(self, label_selector: str | None = None) -> list[object]: ...

    async def get_namespace(self, name: str) -> object: ...

    async def list_pods(self, namespace: str) -> list[object]: ...

    async def get_pod(self, namespace: str, name: str) -> object: ...

    async def list_deployments(self, namespace: str) -> list[object]: ...

    async def list_events(self, namespace: str) -> list[object]: ...

    async def list_ingresses(self, namespace: str) -> list[dict[str, object]]: ...


async def list_tenants(
    k8s_client: K8sReader,
    tier: str | None = None,
    type: str | None = None,
) -> list[Tenant]:
    label_selector = _tenant_label_selector(tier=tier, type=type)
    namespaces = await k8s_client.list_namespaces(label_selector)
    return [_tenant_from_namespace(namespace) for namespace in namespaces]


async def get_tenant(k8s_client: K8sReader, namespace: str) -> Tenant:
    return _tenant_from_namespace(await k8s_client.get_namespace(namespace))


async def list_pods(k8s_client: K8sReader, namespace: str) -> list[PodInfo]:
    pods = await k8s_client.list_pods(namespace)
    return [_pod_info_from_pod(pod) for pod in pods]


async def get_pod(k8s_client: K8sReader, namespace: str, name: str) -> PodInfo:
    return _pod_info_from_pod(await k8s_client.get_pod(namespace, name))


async def list_deployments(k8s_client: K8sReader, namespace: str) -> list[DeploymentInfo]:
    deployments = await k8s_client.list_deployments(namespace)
    return [_deployment_info_from_deployment(deployment) for deployment in deployments]


async def list_ingresses(k8s_client: K8sReader, namespace: str) -> list[IngressInfo]:
    ingresses = await k8s_client.list_ingresses(namespace)
    return [_ingress_info_from_dict(ingress) for ingress in ingresses]


async def get_events(k8s_client: K8sReader, namespace: str) -> list[K8sEvent]:
    events = await k8s_client.list_events(namespace)
    return [_event_from_k8s_event(event) for event in events]


def _tenant_label_selector(tier: str | None = None, type: str | None = None) -> str:
    labels = ["saasphere.io/tenant=true"]
    if tier is not None:
        labels.append(f"saasphere.io/tier={tier}")
    if type is not None:
        labels.append(f"saasphere.io/type={type}")
    return ",".join(labels)


def _tenant_from_namespace(namespace: object) -> Tenant:
    metadata = _get_attr(namespace, "metadata")
    labels = _get_labels(metadata)
    annotations = _get_annotations(metadata)
    return Tenant(
        namespace=_metadata_name(metadata),
        tier=_tier_or_none(labels.get("saasphere.io/tier")),
        type=_tenant_type_or_none(labels.get("saasphere.io/type")),
        owner=annotations.get("saasphere.io/owner"),
        last_active=_datetime_or_none(annotations.get("saasphere.io/last-active")),
        pods_running=0,
        pods_total=0,
        is_scaled_to_zero=labels.get("saasphere.io/scaled-to-zero") == "true",
    )


def _pod_info_from_pod(pod: object) -> PodInfo:
    metadata = _get_attr(pod, "metadata")
    status = _get_attr(pod, "status")
    spec = _get_attr(pod, "spec")
    namespace = _metadata_namespace(metadata)
    container_statuses = [
        _container_status_from_k8s_status(status)
        for status in _sequence_attr(status, "containerStatuses", "container_statuses")
    ]
    ready = bool(container_statuses) and all(status.ready for status in container_statuses)
    restart_count = sum(status.restart_count for status in container_statuses)
    return PodInfo(
        namespace=namespace,
        name=_metadata_name(metadata),
        phase=_str_or_none(_get_attr(status, "phase")),
        ready=ready,
        restart_count=restart_count,
        container_statuses=container_statuses,
        age_seconds=_age_seconds(
            _datetime_attr(metadata, "creationTimestamp", "creation_timestamp")
        ),
        node=_str_or_none(_get_attr(spec, "nodeName", "node_name")),
    )


def _container_status_from_k8s_status(status: object) -> ContainerStatus:
    return ContainerStatus(
        name=_str_or_empty(_get_attr(status, "name")),
        ready=bool(_get_attr(status, "ready")),
        restart_count=_int_or_zero(_get_attr(status, "restartCount", "restart_count")),
        last_state_reason=_last_state_reason(_get_attr(status, "lastState", "last_state")),
    )


def _deployment_info_from_deployment(deployment: object) -> DeploymentInfo:
    metadata = _get_attr(deployment, "metadata")
    spec = _get_attr(deployment, "spec")
    status = _get_attr(deployment, "status")
    return DeploymentInfo(
        namespace=_metadata_namespace(metadata),
        name=_metadata_name(metadata),
        replicas=_int_or_none(_get_attr(spec, "replicas")),
        available_replicas=_int_or_none(
            _get_attr(status, "availableReplicas", "available_replicas")
        ),
        ready_replicas=_int_or_none(_get_attr(status, "readyReplicas", "ready_replicas")),
    )


def _ingress_info_from_dict(ingress: dict[str, object]) -> IngressInfo:
    hosts = ingress.get("hosts")
    return IngressInfo(
        name=_str_or_empty(ingress.get("name")),
        namespace=_str_or_empty(ingress.get("namespace")),
        hosts=[str(host) for host in hosts if isinstance(host, str)]
        if isinstance(hosts, list)
        else [],
        tls=bool(ingress.get("tls")),
        address=_str_or_none(ingress.get("address")),
        age_minutes=_int_or_zero(ingress.get("age_minutes")),
    )


def _event_from_k8s_event(event: object) -> K8sEvent:
    metadata = _get_attr(event, "metadata")
    involved_object = _get_attr(event, "involvedObject", "involved_object")
    return K8sEvent(
        timestamp=_datetime_attr(
            event,
            "eventTime",
            "event_time",
            "lastTimestamp",
            "last_timestamp",
        ),
        namespace=_metadata_namespace(metadata),
        kind=_str_or_none(_get_attr(involved_object, "kind")),
        name=_str_or_none(_get_attr(involved_object, "name")),
        reason=_str_or_none(_get_attr(event, "reason")),
        message=_str_or_none(_get_attr(event, "message")),
        type=_str_or_none(_get_attr(event, "type")),
    )


def _get_attr(obj: object, *names: str) -> object | None:
    for name in names:
        if isinstance(obj, Mapping) and name in obj:
            return cast(object, obj[name])
        value = getattr(obj, name, None)
        if value is not None:
            return cast(object, value)
    return None


def _get_labels(metadata: object | None) -> dict[str, str]:
    return _string_mapping(_get_attr(metadata, "labels"))


def _get_annotations(metadata: object | None) -> dict[str, str]:
    return _string_mapping(_get_attr(metadata, "annotations"))


def _metadata_name(metadata: object | None) -> str:
    return _str_or_empty(_get_attr(metadata, "name"))


def _metadata_namespace(metadata: object | None) -> str:
    return _str_or_empty(_get_attr(metadata, "namespace"))


def _string_mapping(value: object | None) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    return {
        str(key): str(item)
        for key, item in value.items()
        if isinstance(key, str) and isinstance(item, str)
    }


def _tier_or_none(value: str | None) -> Literal["free", "basic", "premium"] | None:
    if value in {"free", "basic", "premium"}:
        return cast(Literal["free", "basic", "premium"], value)
    return None


def _tenant_type_or_none(value: str | None) -> Literal["wordpress", "nextcloud", "custom"] | None:
    if value in {"wordpress", "nextcloud", "custom"}:
        return cast(Literal["wordpress", "nextcloud", "custom"], value)
    return None


def _datetime_or_none(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _datetime_attr(obj: object | None, *names: str) -> datetime | None:
    value = _get_attr(obj, *names)
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        return _datetime_or_none(value)
    return None


def _age_seconds(created_at: datetime | None) -> int | None:
    if created_at is None:
        return None
    return max(0, int((datetime.now(UTC) - created_at).total_seconds()))


def _sequence_attr(obj: object | None, *names: str) -> Sequence[object]:
    value = _get_attr(obj, *names)
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return value
    return []


def _last_state_reason(last_state: object | None) -> str | None:
    if last_state is None:
        return None
    for state_name in ("terminated", "waiting", "running"):
        state = _get_attr(last_state, state_name)
        reason = _str_or_none(_get_attr(state, "reason"))
        if reason is not None:
            return reason
    return None


def _str_or_none(value: object | None) -> str | None:
    return value if isinstance(value, str) else None


def _str_or_empty(value: object | None) -> str:
    return value if isinstance(value, str) else ""


def _int_or_none(value: object | None) -> int | None:
    return value if isinstance(value, int) else None


def _int_or_zero(value: object | None) -> int:
    return value if isinstance(value, int) else 0

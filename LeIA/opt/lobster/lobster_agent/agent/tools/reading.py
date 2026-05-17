from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal, Protocol, cast
from uuid import UUID

from pydantic import BaseModel, Field
from pydantic_ai import RunContext

from lobster_agent.agent.deps import AgentDeps
from lobster_agent.agent.tools import k8s_read
from lobster_agent.clients.alertmanager import AlertmanagerError
from lobster_agent.clients.k8s import K8sClientError
from lobster_agent.clients.loki import LogEntry, LokiClient, LokiQueryError
from lobster_agent.clients.prometheus import PrometheusClient, PrometheusQueryError
from lobster_agent.domain.models import (
    DeploymentInfo,
    GlobalHealth,
    IngressInfo,
    LogEntryPublic,
    NodeMetrics,
    PodInfo,
    TenantMetrics,
)
from lobster_agent.domain.models import (
    K8sEvent as DomainK8sEvent,
)


class PrometheusReader(Protocol):
    async def instant_query(self, query: str) -> list[dict[str, object]]: ...


class LokiReader(Protocol):
    async def query_range(
        self,
        logql: str,
        start: datetime,
        end: datetime,
        limit: int = 100,
    ) -> list[LogEntry]: ...


class ToolError(BaseModel):
    source: str
    message: str


class PromSeriesValue(BaseModel):
    metric: dict[str, str]
    value: float | str | None = None


class PromInstantResult(BaseModel):
    query: str
    series_count: int
    values: list[PromSeriesValue]


class PromRangeResult(BaseModel):
    query: str
    minutes: int
    series_count: int
    values: list[PromSeriesValue]


class NodeHealth(BaseModel):
    node: Literal["leia", "matrix", "sauron", "heimdall", "fallback"]
    cpu_pct: float
    memory_pct: float


class NodeAliveness(BaseModel):
    node: Literal["matrix", "fallback"]
    alive: bool
    detail: str


class LogLine(BaseModel):
    timestamp: datetime
    labels: dict[str, str]
    line: str


class LokiQueryResult(BaseModel):
    logql: str
    minutes: int
    lines: list[LogLine]


class PodSummary(BaseModel):
    name: str
    namespace: str
    phase: str | None
    restarts: int
    age_minutes: int | None
    container_statuses_brief: str


class PodDetail(PodSummary):
    ready: bool
    node: str | None


class DeploymentSummary(BaseModel):
    name: str
    namespace: str
    replicas: int | None
    ready_replicas: int | None
    available_replicas: int | None


class IngressSummary(BaseModel):
    name: str
    namespace: str
    hosts: list[str]
    tls: bool
    address: str | None
    age_minutes: int


class K8sEvent(BaseModel):
    type: str | None
    reason: str | None
    object: str
    message: str | None
    age_minutes: int | None


class NamespaceInfo(BaseModel):
    name: str


class AlertSummary(BaseModel):
    fingerprint: str
    severity: str | None
    summary: str | None
    labels: dict[str, str]
    age_minutes: int


class AlertDetail(AlertSummary):
    annotations: dict[str, str]
    starts_at: datetime
    ends_at: datetime | None
    generator_url: str | None
    status: str


class DecisionSummary(BaseModel):
    id: str
    timestamp: datetime
    case_use: str
    prompt_summary: str
    conclusion: str
    tools_called: list[str]


class DecisionDetail(DecisionSummary):
    reasoning: str | None
    model_used: str
    think_mode: bool


async def query_prometheus(
    prom_client: PrometheusClient | PrometheusReader,
    query: str,
) -> list[dict[str, object]]:
    return await prom_client.instant_query(query)


async def query_prometheus_instant(
    ctx: RunContext[AgentDeps],
    query: str,
) -> PromInstantResult | ToolError:
    """Run an instant Prometheus query and return a compact result."""
    try:
        results = await query_prometheus(ctx.deps.prometheus, query)
    except PrometheusQueryError as exc:
        return ToolError(source="prometheus", message=str(exc))
    return PromInstantResult(
        query=query,
        series_count=len(results),
        values=[_prom_series_value(item) for item in results],
    )


async def query_prometheus_range(
    ctx: RunContext[AgentDeps],
    query: str,
    minutes: Annotated[int, Field(ge=1, le=360)],
) -> PromRangeResult | ToolError:
    """Run a Prometheus range query for the last minutes, from 1 to 360."""
    end = datetime.now(UTC)
    start = end - timedelta(minutes=minutes)
    try:
        results = await ctx.deps.prometheus.range_query(query, start, end, "30s")
    except PrometheusQueryError as exc:
        return ToolError(source="prometheus", message=str(exc))
    return PromRangeResult(
        query=query,
        minutes=minutes,
        series_count=len(results),
        values=[_prom_series_value(item) for item in results],
    )


async def get_node_health(
    ctx: RunContext[AgentDeps],
    node: Literal["leia", "matrix", "sauron", "heimdall", "fallback"],
) -> NodeHealth | ToolError:
    """Read current CPU and memory health for a known SaaSphere node."""
    try:
        metrics = await get_node_metrics(ctx.deps.prometheus, node)
    except PrometheusQueryError as exc:
        return ToolError(source="prometheus", message=str(exc))
    return NodeHealth(node=node, cpu_pct=metrics.cpu_pct, memory_pct=metrics.memory_pct)


async def is_node_alive(
    ctx: RunContext[AgentDeps],
    node: Literal["matrix", "fallback"],
) -> NodeAliveness | ToolError:
    """Check whether a K3s node is Ready according to Kubernetes itself.

    Returns alive=True when the node's Ready condition is "True". A node that
    is powered off, unreachable, or whose kubelet is down will be reported as
    alive=False — even if Prometheus metrics still look fine for stale data.
    """
    try:
        ready = await ctx.deps.k8s.get_node_ready(node)
    except K8sClientError as exc:
        return ToolError(source="k8s", message=str(exc))
    detail = (
        "Node Ready=True" if ready else "Node not Ready (powered off, unreachable, or kubelet down)"
    )
    return NodeAliveness(node=node, alive=ready, detail=detail)


async def query_loki(
    loki_client: LokiClient | LokiReader,
    logql: str,
    start: datetime,
    end: datetime,
    limit: int = 100,
) -> list[LogEntryPublic]:
    entries = await loki_client.query_range(logql, start, end, limit)
    return [
        LogEntryPublic(timestamp=entry.timestamp, labels=entry.labels, line=entry.line)
        for entry in entries
    ]


async def query_loki_logs(
    ctx: RunContext[AgentDeps],
    logql: str,
    minutes: Annotated[int, Field(ge=1, le=360)] = 15,
    limit: Annotated[int, Field(ge=1, le=1000)] = 100,
) -> LokiQueryResult | ToolError:
    """Query Loki logs over the last minutes and return compact log lines."""
    end = datetime.now(UTC)
    start = end - timedelta(minutes=minutes)
    try:
        entries = await query_loki(ctx.deps.loki, logql, start, end, limit)
    except LokiQueryError as exc:
        return ToolError(source="loki", message=str(exc))
    return LokiQueryResult(
        logql=logql,
        minutes=minutes,
        lines=[
            LogLine(
                timestamp=entry.timestamp,
                labels=entry.labels,
                line=_truncate(entry.line),
            )
            for entry in entries
        ],
    )


async def get_recent_errors(
    ctx: RunContext[AgentDeps],
    service: str,
    minutes: int = 15,
) -> list[LogLine] | ToolError:
    """Return recent error log lines for a service from Loki."""
    result = await query_loki_logs(
        ctx,
        f'{{service="{service}"}} |~ "(?i)error|exception|failed"',
        minutes,
        100,
    )
    if isinstance(result, ToolError):
        return result
    return result.lines


async def list_pods(
    ctx: RunContext[AgentDeps],
    namespace: str | None = None,
) -> list[PodSummary] | ToolError:
    """List Kubernetes pods with phase, restarts, age, and container status."""
    try:
        pods = await _pods_for_namespace(ctx, namespace)
    except K8sClientError as exc:
        return ToolError(source="k8s", message=str(exc))
    return [_pod_summary(pod) for pod in pods]


async def get_pod(ctx: RunContext[AgentDeps], namespace: str, name: str) -> PodDetail | ToolError:
    """Read detailed Kubernetes pod status for one pod."""
    try:
        pod = await k8s_read.get_pod(ctx.deps.k8s, namespace, name)
    except K8sClientError as exc:
        return ToolError(source="k8s", message=str(exc))
    summary = _pod_summary(pod)
    return PodDetail(
        **summary.model_dump(),
        ready=pod.ready,
        node=pod.node,
    )


async def list_deployments(
    ctx: RunContext[AgentDeps],
    namespace: str | None = None,
) -> list[DeploymentSummary] | ToolError:
    """List Kubernetes deployments with replica readiness."""
    try:
        deployments = await _deployments_for_namespace(ctx, namespace)
    except K8sClientError as exc:
        return ToolError(source="k8s", message=str(exc))
    return [_deployment_summary(deployment) for deployment in deployments]


async def list_ingresses(
    ctx: RunContext[AgentDeps],
    namespace: str | None = None,
) -> list[IngressSummary] | ToolError:
    """List Kubernetes ingresses with hosts, TLS, and assigned address."""
    try:
        ingresses = await _ingresses_for_namespace(ctx, namespace)
    except K8sClientError as exc:
        return ToolError(source="k8s", message=str(exc))
    return [_ingress_summary(ingress) for ingress in ingresses]


async def list_recent_events(
    ctx: RunContext[AgentDeps],
    namespace: str | None = None,
    minutes: int = 30,
) -> list[K8sEvent] | ToolError:
    """List recent Kubernetes events for a namespace or all namespaces."""
    try:
        events = await _events_for_namespace(ctx, namespace)
    except K8sClientError as exc:
        return ToolError(source="k8s", message=str(exc))
    cutoff = datetime.now(UTC) - timedelta(minutes=minutes)
    return [_event_summary(event) for event in events if _event_after(event, cutoff)]


async def list_namespaces(ctx: RunContext[AgentDeps]) -> list[NamespaceInfo] | ToolError:
    """List Kubernetes namespaces visible to Lobster."""
    try:
        namespaces = await ctx.deps.k8s.list_namespaces()
    except K8sClientError as exc:
        return ToolError(source="k8s", message=str(exc))
    return [NamespaceInfo(name=_metadata_name(namespace)) for namespace in namespaces]


async def list_active_alerts(
    ctx: RunContext[AgentDeps],
    severity: Literal["info", "warning", "critical"] | None = None,
) -> list[AlertSummary] | ToolError:
    """List active Alertmanager alerts, optionally filtered by severity."""
    filters: dict[str, str] | None = {"severity": severity} if severity is not None else None
    try:
        alerts = await ctx.deps.alertmanager.list_active_alerts(filters)
    except AlertmanagerError as exc:
        return ToolError(source="alertmanager", message=str(exc))
    return [_alert_summary(alert) for alert in alerts]


async def get_alert_details(
    ctx: RunContext[AgentDeps],
    fingerprint: str,
) -> AlertDetail | ToolError:
    """Read detailed Alertmanager information for one alert fingerprint."""
    try:
        alert = await ctx.deps.alertmanager.get_alert_by_fingerprint(fingerprint)
    except AlertmanagerError as exc:
        return ToolError(source="alertmanager", message=str(exc))
    if alert is None:
        return ToolError(source="alertmanager", message=f"alert {fingerprint} not found")
    summary = _alert_summary(alert)
    return AlertDetail(
        **summary.model_dump(),
        annotations={key: _truncate(value) for key, value in alert.annotations.items()},
        starts_at=alert.starts_at,
        ends_at=alert.ends_at,
        generator_url=alert.generator_url,
        status=alert.status,
    )


async def search_decisions(
    ctx: RunContext[AgentDeps],
    case_use: str | None = None,
    limit: Annotated[int, Field(ge=1, le=50)] = 10,
) -> list[DecisionSummary] | ToolError:
    """Search recent persisted Lobster decisions, optionally by case use."""
    try:
        if case_use is None:
            decisions = await ctx.deps.decisions_repo.list_recent(limit)
        else:
            decisions = await ctx.deps.decisions_repo.list_by_case_use(case_use, limit)
    except RuntimeError as exc:
        return ToolError(source="memory", message=str(exc))
    return [_decision_summary(decision) for decision in decisions]


async def get_decision(
    ctx: RunContext[AgentDeps],
    decision_id: str,
) -> DecisionDetail | None | ToolError:
    """Read one persisted Lobster decision by UUID."""
    try:
        parsed_id = UUID(decision_id)
    except ValueError:
        return ToolError(source="memory", message=f"invalid decision id: {decision_id}")
    try:
        decision = await ctx.deps.decisions_repo.get_by_id(parsed_id)
    except RuntimeError as exc:
        return ToolError(source="memory", message=str(exc))
    if decision is None:
        return None
    summary = _decision_summary(decision)
    return DecisionDetail(
        **summary.model_dump(),
        reasoning=decision.reasoning,
        model_used=decision.model_used,
        think_mode=decision.think_mode,
    )


async def get_node_metrics(
    prom_client: PrometheusClient | PrometheusReader,
    node_name: str,
) -> NodeMetrics:
    cpu_query = (
        "100 - avg by(instance)("
        f'rate(node_cpu_seconds_total{{mode="idle",instance="{node_name}"}}[5m])'
        ") * 100"
    )
    memory_query = (
        "100 * (1 - "
        f'(node_memory_MemAvailable_bytes{{instance="{node_name}"}} / '
        f'node_memory_MemTotal_bytes{{instance="{node_name}"}})'
        ")"
    )

    cpu_result = await prom_client.instant_query(cpu_query)
    memory_result = await prom_client.instant_query(memory_query)

    return NodeMetrics(
        node=node_name,
        cpu_pct=_first_prometheus_value(cpu_result, default=0.0),
        memory_pct=_first_prometheus_value(memory_result, default=0.0),
    )


async def get_global_health(prom_client: PrometheusClient | PrometheusReader) -> GlobalHealth:
    results = await prom_client.instant_query("up")
    nodes = _nodes_from_up_results(results)
    return GlobalHealth(
        timestamp=datetime.now(UTC),
        nodes=nodes,
        total_tenants=None,
        tenants_active=None,
        active_alerts=None,
    )


async def get_tenant_metrics(
    prom_client: PrometheusClient | PrometheusReader,
    namespace: str,
) -> TenantMetrics:
    _ = prom_client
    # TODO: Fill CPU, memory, request, error, and latency PromQL once ingress/K8s
    # metric names are fixed for SaaSphere tenants.
    return TenantMetrics(namespace=namespace)


def _first_prometheus_value(results: list[dict[str, object]], default: float) -> float:
    if not results:
        return default

    value = results[0].get("value")
    if not isinstance(value, list) or len(value) < 2:
        return default

    raw = value[1]
    if not isinstance(raw, str | int | float):
        return default

    try:
        return float(raw)
    except ValueError:
        return default


def _nodes_from_up_results(results: list[dict[str, object]]) -> list[NodeMetrics]:
    nodes: list[NodeMetrics] = []
    seen: set[str] = set()
    for result in results:
        metric = result.get("metric")
        if not isinstance(metric, dict):
            continue

        node = _node_name_from_metric(metric)
        if node is None or node in seen:
            continue

        seen.add(node)
        nodes.append(NodeMetrics(node=node, cpu_pct=0.0, memory_pct=0.0))
    return nodes


def _node_name_from_metric(metric: dict[object, object]) -> str | None:
    for key in ("instance", "node"):
        value = metric.get(key)
        if isinstance(value, str) and value:
            return value
    return None


async def _pods_for_namespace(
    ctx: RunContext[AgentDeps],
    namespace: str | None,
) -> list[PodInfo]:
    if namespace is not None:
        return await k8s_read.list_pods(ctx.deps.k8s, namespace)

    pods: list[PodInfo] = []
    namespaces = await list_namespaces(ctx)
    if isinstance(namespaces, ToolError):
        raise K8sClientError(namespaces.message)
    for item in namespaces:
        pods.extend(await k8s_read.list_pods(ctx.deps.k8s, item.name))
    return pods


async def _deployments_for_namespace(
    ctx: RunContext[AgentDeps],
    namespace: str | None,
) -> list[DeploymentInfo]:
    if namespace is not None:
        return await k8s_read.list_deployments(ctx.deps.k8s, namespace)

    deployments: list[DeploymentInfo] = []
    namespaces = await list_namespaces(ctx)
    if isinstance(namespaces, ToolError):
        raise K8sClientError(namespaces.message)
    for item in namespaces:
        deployments.extend(await k8s_read.list_deployments(ctx.deps.k8s, item.name))
    return deployments


async def _ingresses_for_namespace(
    ctx: RunContext[AgentDeps],
    namespace: str | None,
) -> list[IngressInfo]:
    if namespace is not None:
        return await k8s_read.list_ingresses(ctx.deps.k8s, namespace)

    ingresses: list[IngressInfo] = []
    namespaces = await list_namespaces(ctx)
    if isinstance(namespaces, ToolError):
        raise K8sClientError(namespaces.message)
    for item in namespaces:
        ingresses.extend(await k8s_read.list_ingresses(ctx.deps.k8s, item.name))
    return ingresses


async def _events_for_namespace(
    ctx: RunContext[AgentDeps],
    namespace: str | None,
) -> list[DomainK8sEvent]:
    if namespace is not None:
        return await k8s_read.get_events(ctx.deps.k8s, namespace)

    events: list[DomainK8sEvent] = []
    namespaces = await list_namespaces(ctx)
    if isinstance(namespaces, ToolError):
        raise K8sClientError(namespaces.message)
    for item in namespaces:
        events.extend(await k8s_read.get_events(ctx.deps.k8s, item.name))
    return events


def _prom_series_value(item: dict[str, object]) -> PromSeriesValue:
    metric = item.get("metric")
    value = item.get("value")
    raw_value: object | None = None
    if isinstance(value, list) and len(value) >= 2:
        raw_value = value[1]
    elif "values" in item:
        raw_value = "range"
    return PromSeriesValue(
        metric=_string_mapping(metric),
        value=_float_or_string(raw_value),
    )


def _pod_summary(pod: PodInfo) -> PodSummary:
    return PodSummary(
        name=pod.name,
        namespace=pod.namespace,
        phase=pod.phase,
        restarts=pod.restart_count,
        age_minutes=_seconds_to_minutes(pod.age_seconds),
        container_statuses_brief=_truncate(
            ", ".join(
                f"{status.name}:ready={status.ready},restarts={status.restart_count}"
                for status in pod.container_statuses
            )
        ),
    )


def _deployment_summary(deployment: DeploymentInfo) -> DeploymentSummary:
    return DeploymentSummary(
        name=deployment.name,
        namespace=deployment.namespace,
        replicas=deployment.replicas,
        ready_replicas=deployment.ready_replicas,
        available_replicas=deployment.available_replicas,
    )


def _ingress_summary(ingress: IngressInfo) -> IngressSummary:
    return IngressSummary(
        name=ingress.name,
        namespace=ingress.namespace,
        hosts=ingress.hosts,
        tls=ingress.tls,
        address=ingress.address,
        age_minutes=ingress.age_minutes,
    )


def _event_summary(event: DomainK8sEvent) -> K8sEvent:
    obj = "/".join(part for part in (event.kind, event.name) if part)
    return K8sEvent(
        type=event.type,
        reason=event.reason,
        object=obj,
        message=_truncate(event.message) if event.message is not None else None,
        age_minutes=_age_minutes(event.timestamp),
    )


def _event_after(event: DomainK8sEvent, cutoff: datetime) -> bool:
    if event.timestamp is None:
        return True
    timestamp = (
        event.timestamp
        if event.timestamp.tzinfo is not None
        else event.timestamp.replace(tzinfo=UTC)
    )
    return timestamp >= cutoff


def _alert_summary(alert: object) -> AlertSummary:
    starts_at = cast(datetime, getattr(alert, "starts_at"))
    labels = cast(dict[str, str], getattr(alert, "labels"))
    annotations = cast(dict[str, str], getattr(alert, "annotations"))
    summary = annotations.get("summary")
    return AlertSummary(
        fingerprint=cast(str, getattr(alert, "fingerprint")),
        severity=cast(str | None, getattr(alert, "severity")),
        summary=_truncate(summary) if summary is not None else None,
        labels={
            key: value
            for key, value in labels.items()
            if key in {"alertname", "severity", "namespace", "pod", "instance", "job"}
        },
        age_minutes=_age_minutes(starts_at) or 0,
    )


def _decision_summary(decision: object) -> DecisionSummary:
    return DecisionSummary(
        id=str(getattr(decision, "id")),
        timestamp=getattr(decision, "timestamp"),
        case_use=getattr(decision, "case_use"),
        prompt_summary=_truncate(getattr(decision, "prompt_summary")),
        conclusion=_truncate(getattr(decision, "conclusion")),
        tools_called=list(getattr(decision, "tools_called", [])),
    )


def _metadata_name(namespace: object) -> str:
    metadata = getattr(namespace, "metadata", None)
    value = getattr(metadata, "name", None)
    return value if isinstance(value, str) else ""


def _string_mapping(value: object | None) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        key: item for key, item in value.items() if isinstance(key, str) and isinstance(item, str)
    }


def _float_or_string(value: object | None) -> float | str | None:
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return _truncate(value)
    return None


def _seconds_to_minutes(seconds: int | None) -> int | None:
    if seconds is None:
        return None
    return seconds // 60


def _age_minutes(timestamp: datetime | None) -> int | None:
    if timestamp is None:
        return None
    aware = timestamp if timestamp.tzinfo is not None else timestamp.replace(tzinfo=UTC)
    return max(0, int((datetime.now(UTC) - aware).total_seconds() // 60))


def _truncate(value: str, limit: int = 500) -> str:
    return value if len(value) <= limit else f"{value[: limit - 1]}…"

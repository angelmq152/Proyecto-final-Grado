from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class LogEntryPublic(BaseModel):
    timestamp: datetime
    labels: dict[str, str]
    line: str


class NodeMetrics(BaseModel):
    node: str
    cpu_pct: float
    memory_pct: float
    disk_pct: float | None = None
    network_in_bps: int | None = None
    network_out_bps: int | None = None
    pods_running: int | None = None


class TenantMetrics(BaseModel):
    namespace: str
    cpu_avg: float | None = None
    memory_avg: float | None = None
    requests_total: int | None = None
    errors_total: int | None = None
    error_rate_pct: float | None = None
    p95_latency_ms: float | None = None


class GlobalHealth(BaseModel):
    timestamp: datetime
    nodes: list[NodeMetrics]
    total_tenants: int | None = None
    tenants_active: int | None = None
    active_alerts: int | None = None


class AlertInfo(BaseModel):
    name: str
    severity: str
    state: str | None = None
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)


class Tenant(BaseModel):
    namespace: str
    tier: Literal["free", "basic", "premium"] | None = None
    type: Literal["wordpress", "nextcloud", "custom"] | None = None
    owner: str | None = None
    last_active: datetime | None = None
    pods_running: int = 0
    pods_total: int = 0
    is_scaled_to_zero: bool = False


class ContainerStatus(BaseModel):
    name: str
    ready: bool
    restart_count: int
    last_state_reason: str | None = None


class PodInfo(BaseModel):
    namespace: str
    name: str
    phase: str | None = None
    ready: bool = False
    restart_count: int = 0
    container_statuses: list[ContainerStatus] = Field(default_factory=list)
    age_seconds: int | None = None
    node: str | None = None


class DeploymentInfo(BaseModel):
    namespace: str
    name: str
    replicas: int | None = None
    available_replicas: int | None = None
    ready_replicas: int | None = None


class IngressInfo(BaseModel):
    name: str
    namespace: str
    hosts: list[str] = Field(default_factory=list)
    tls: bool = False
    address: str | None = None
    age_minutes: int = 0


class K8sEvent(BaseModel):
    timestamp: datetime | None = None
    namespace: str
    kind: str | None = None
    name: str | None = None
    reason: str | None = None
    message: str | None = None
    type: str | None = None


class CertificateInfo(BaseModel):
    domain: str
    issuer: str | None = None
    expires_at: datetime
    days_until_expiration: int
    is_expired: bool = False
    source: str | None = None

import time

from prometheus_client import REGISTRY, Counter, Gauge, Histogram, generate_latest  # noqa: F401

START_TIME = time.time()

lobster_info = Gauge("lobster_info", "Lobster version info", ["version"])
lobster_uptime_seconds = Gauge("lobster_uptime_seconds", "Uptime in seconds")
lobster_errors_total = Counter("lobster_errors_total", "Total errors", ["component", "severity"])
lobster_http_requests_total = Counter(
    "lobster_http_requests_total", "HTTP requests to Lobster", ["endpoint", "status"]
)
lobster_decisions_total = Counter(
    "lobster_decisions_total", "Agent decisions", ["case_use", "model", "think", "outcome"]
)
lobster_llm_latency_seconds = Histogram(
    "lobster_llm_latency_seconds",
    "LLM request latency in seconds",
    ["case_use", "model"],
    buckets=[1, 2, 5, 10, 20, 30, 60, 120, 180, 300, 600],
)
lobster_llm_tokens_total = Counter(
    "lobster_llm_tokens_total", "LLM tokens", ["case_use", "model", "direction"]
)
lobster_last_cycle_timestamp = Gauge(
    "lobster_last_cycle_timestamp",
    "Unix timestamp of the last completed scheduled cycle",
    ["case_use"],
)
lobster_scheduler_runs_total = Counter(
    "lobster_scheduler_runs_total",
    "Total scheduled job executions",
    ["case_use", "outcome"],
)
lobster_webhook_alerts_total = Counter(
    "lobster_webhook_alerts_total",
    "Total Alertmanager webhook alerts received",
    ["status"],
)
lobster_webhook_self_alerts_dropped_total = Counter(
    "lobster_webhook_self_alerts_dropped_total",
    "Alertmanager webhook payloads dropped because they are Lobster self-monitoring alerts",
    ["alertname"],
)
lobster_approvals_pending = Gauge(
    "lobster_approvals_pending",
    "Number of approvals currently in PENDING state",
)
lobster_loki_queue_size = Gauge(
    "lobster_loki_queue_size",
    "Number of log entries waiting in the Loki push queue",
)


def init_metrics(version: str) -> None:
    lobster_info.labels(version=version).set(1)


def update_uptime() -> None:
    lobster_uptime_seconds.set(time.time() - START_TIME)


def get_metrics() -> bytes:
    update_uptime()
    return generate_latest()

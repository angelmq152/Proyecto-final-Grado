# Lobster

**AI infrastructure orchestration agent for SaaSphere.**

Lobster monitors K3s tenant namespaces via Prometheus and Loki, reasons with Qwen3 running on Ollama, and autonomously manages container lifecycle on a self-hosted homelab.

## Stack

- **Language:** Python 3.13 + uv
- **Agent:** Pydantic AI
- **Server:** FastAPI + Uvicorn
- **K8s client:** lightkube
- **Scheduler:** APScheduler
- **Telegram:** aiogram v3
- **DB:** SQLite + SQLModel
- **Logging:** structlog → Loki
- **Metrics:** prometheus-client
- **Supervisor:** systemd

## Development

```bash
uv sync
uv run pytest
uv run ruff check .
uv run mypy lobster_agent/
```

## Metrics

Lobster exposes Prometheus metrics at `GET /metrics` (default port 8081).

| Metric | Type | Labels | Description |
|---|---|---|---|
| `lobster_info` | Gauge | `version` | Always 1; carries the running version |
| `lobster_uptime_seconds` | Gauge | — | Seconds since process start |
| `lobster_decisions_total` | Counter | `case_use`, `model`, `think`, `outcome` | LLM inference cycles completed |
| `lobster_llm_latency_seconds` | Histogram | `case_use`, `model` | End-to-end LLM call duration |
| `lobster_llm_tokens_total` | Counter | `case_use`, `model`, `direction` | Tokens consumed (`direction`: `input`/`output`) |
| `lobster_scheduler_runs_total` | Counter | `case_use`, `outcome` | Scheduled job executions |
| `lobster_last_cycle_timestamp` | Gauge | `case_use` | Unix timestamp of the last completed job per case |
| `lobster_webhook_alerts_total` | Counter | `status` | Alertmanager webhook alerts received |
| `lobster_http_requests_total` | Counter | `endpoint`, `status` | HTTP requests served by FastAPI |
| `lobster_errors_total` | Counter | `component`, `severity` | Unexpected exceptions (`component`: `agent`/`scheduler`/`k8s_watcher`) |

See `docs/fase_7_metrica_*.md` for per-metric query examples and Sauron integration instructions.

## Alerts

Prometheus alert rules are in `deploy/prometheus/lobster.rules.yaml`.
See `docs/fase_7_alertas_prometheus.md` for installation steps on Sauron.

Alerts defined:

| Alert | Severity | Condition |
|---|---|---|
| `LobsterSinActividad` | critical | No job cycle for > 15 min |
| `LobsterTasaErroresAlta` | warning | Error rate > 0.05/s for 3 min |
| `LobsterLatenciaLLMAlta` | warning | LLM p95 latency > 5 min for 5 min |
| `LobsterDecisionesFallidas` | warning | > 30% failed decisions over 10 min |
| `LobsterRestart` | info | Process uptime < 2 min |

## Grafana Dashboard

Import `deploy/grafana/lobster-dashboard.json` into Grafana on Sauron.
See `docs/fase_7_dashboard_grafana.md` for import options (UI / API / provisioning).

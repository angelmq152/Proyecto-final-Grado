---
title: Observabilidad — Métricas Prometheus
tags: [observabilidad, metrics, prometheus, fase7]
---

# 📈 Métricas · Prometheus

> [!abstract] Lobster expone 10+ métricas
> Archivo: `lobster_agent/observability/metrics.py`. Todas se inicializan a nivel módulo (singletons) y se exponen en `GET /metrics`. Sauron las scrapea cada 15 s.

## 📋 Tabla completa

| Métrica | Tipo | Labels | Qué mide |
|---|---|---|---|
| `lobster_info` | Gauge | `version` | Siempre 1. Permite filtrar por versión. |
| `lobster_uptime_seconds` | Gauge | — | Segundos desde arranque |
| `lobster_errors_total` | Counter | `component`, `severity` | Excepciones imprevistas |
| `lobster_http_requests_total` | Counter | `endpoint`, `status` | Reqs HTTP servidas (middleware) |
| `lobster_decisions_total` | Counter | `case_use`, `model`, `think`, `outcome` | Ciclos LLM completados |
| `lobster_llm_latency_seconds` | Histogram | `case_use`, `model` | Latencia LLM end-to-end |
| `lobster_llm_tokens_total` | Counter | `case_use`, `model`, `direction` | Tokens de entrada y salida |
| `lobster_last_cycle_timestamp` | Gauge | `case_use` | Unix ts del último ciclo OK |
| `lobster_scheduler_runs_total` | Counter | `case_use`, `outcome` | Ejecuciones del scheduler |
| `lobster_webhook_alerts_total` | Counter | `status` | Alerts recibidas por webhook |
| `lobster_approvals_pending` | Gauge | — | Aprobaciones en PENDING ahora mismo |
| `lobster_loki_queue_size` | Gauge | — | Backlog del flusher de logs |

## 🪣 Buckets del histograma

```python
lobster_llm_latency_seconds = Histogram(
    "lobster_llm_latency_seconds",
    "LLM request latency in seconds",
    ["case_use", "model"],
    buckets=[1, 2, 5, 10, 20, 30, 60, 120, 180, 300, 600],
)
```

Adaptados al rango real: desde 1 s (8b corto) hasta 10 min (32b daily_summary).

## 🔗 Quién incrementa cada métrica

| Métrica | Quién la mueve |
|---|---|
| `lobster_decisions_total` | `LobsterAgent._record_metrics` |
| `lobster_llm_latency_seconds` | mismo |
| `lobster_llm_tokens_total` | mismo |
| `lobster_errors_total` | scheduler / watcher / agent en `except` |
| `lobster_scheduler_runs_total` | `SchedulerRunner._run_scheduled_job` |
| `lobster_last_cycle_timestamp` | mismo (al finalizar OK) |
| `lobster_webhook_alerts_total` | `main.py:alert_webhook` |
| `lobster_http_requests_total` | middleware en `main.py` |
| `lobster_approvals_pending` | `ApprovalMaintenanceLoop.tick` |
| `lobster_loki_queue_size` | `_flush_loop` cada 5 s |

## 🧮 PromQL útiles

```promql
# QPS de decisiones por modo
sum(rate(lobster_decisions_total[5m])) by (case_use)

# % de outcomes failed
sum(rate(lobster_decisions_total{outcome="failed"}[10m]))
/
sum(rate(lobster_decisions_total[10m]))

# p95 latencia LLM por modelo
histogram_quantile(0.95,
  sum(rate(lobster_llm_latency_seconds_bucket[10m])) by (le, model))

# Tokens/h emitidos
sum(rate(lobster_llm_tokens_total{direction="output"}[1h])) * 3600
```

## 📥 Endpoint

```python
@app.get("/metrics")
async def metrics() -> PlainTextResponse:
    return PlainTextResponse(get_metrics().decode(),
                             media_type="text/plain; version=0.0.4; charset=utf-8")
```

`get_metrics()` llama `update_uptime()` antes de `generate_latest()` para garantizar uptime fresco.

## 🚏 Configuración del scrape

En Sauron, `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: lobster
    scrape_interval: 15s
    static_configs:
      - targets: ["192.168.1.200:8080"]
```

→ Continúa en [[03-Dashboard-Grafana]] y [[04-Alertas-Prometheus]].

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A self-hosted monitoring stack for the **SaaSphere / sauron** homelab. All services run via Docker Compose on the `monitoring` bridge network. Credentials live in `.env` (not committed).

## Stack and ports

| Service | Image | Port |
|---|---|---|
| Prometheus | prom/prometheus:v2.55.1 | 9090 |
| Grafana | grafana/grafana:11.3.1 | 3000 |
| Loki | grafana/loki:3.2.1 | 3100 |
| Promtail | grafana/promtail:3.2.1 | — |
| Blackbox Exporter | prom/blackbox-exporter:v0.25.0 | 9115 |
| Alertmanager | prom/alertmanager:v0.27.0 | 9093 |

## Common commands

```bash
# Start the stack
docker compose up -d

# Stop the stack
docker compose down

# View logs for a specific service
docker compose logs -f prometheus

# Reload Prometheus config without restarting (--web.enable-lifecycle is set)
curl -X POST http://localhost:9090/-/reload

# Check Alertmanager config validity
docker compose exec alertmanager amtool check-config /etc/alertmanager/alertmanager.yml

# Check Prometheus rule syntax
docker compose exec prometheus promtool check rules /etc/prometheus/rules/saasphere.yml
```

## Architecture

**Metrics flow:** node_exporter on each host → Prometheus scrapes every 15s → Grafana queries Prometheus → Alertmanager receives firing alerts → Telegram bot notification.

**Logs flow:** Promtail tails `/var/log/syslog` and `/var/log/auth.log` on the sauron host → pushes to Loki → Grafana queries Loki.

**Probing:** Blackbox Exporter handles ICMP ping and HTTP 2xx checks. ICMP targets are the four non-sauron nodes. HTTP targets (`blackbox_http` job) are currently empty — add URLs there to monitor endpoints.

## Monitored nodes

| Instance | IP | Node Exporter |
|---|---|---|
| sauron (this host) | 192.168.1.201 | :9100 |
| matrix (k8s) | 192.168.1.202 | :9100, kube-state-metrics :30080 |
| heimdall | 192.168.1.203 | :9100 |
| leia | 192.168.1.200 | :9100 |
| fallback | 192.168.1.210 | :9100 |

## Alert rules (`prometheus/rules/saasphere.yml`)

All alerts route to Telegram. Two rule groups:

- **nodos:** `NodoInaccesible` (up==0 for 2m, critical), `MemoriaAlta` (>85% for 5m), `DiscoLleno` (root fs >85% for 5m), `CargaCPUAlta` (>85% for 5m)
- **kubernetes:** `PodCaido` (Failed/Unknown phase for 2m, critical), `PodReiniciando` (>3 restarts in 15m for 5m)

## Grafana provisioning

Datasources and dashboards are fully provisioned from config — no manual setup needed after `docker compose up`. Dashboard JSON files in `grafana/dashboards/` are auto-loaded into the **SaaSphere** folder and polled for changes every 30s.

## Data retention

- Prometheus: 30 days (`--storage.tsdb.retention.time=30d`)
- Loki: 30 days (`retention_period: 720h`), old samples rejected after 7 days (`reject_old_samples_max_age: 168h`)

## Adding HTTP endpoint monitoring

Add the target URL to the `blackbox_http` job in `prometheus/prometheus.yml`, then reload Prometheus:

```yaml
- job_name: 'blackbox_http'
  static_configs:
    - targets:
        - https://example.com
```

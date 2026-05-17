# Sauron

Nodo de **observabilidad** del homelab SaaSphere.

## Servicios

- **Prometheus** — Scrapes de exporters en cada nodo (node_exporter, cadvisor, kube-state-metrics, métricas custom de Lobster en `LeIA:8000/metrics`).
- **Grafana** — Dashboards de infraestructura, K3s, tenants y agente Lobster.
- **Loki** — Agregación de logs.
- **Alertmanager** — Routing dual: alertas internas → Lobster (`/webhook/alert`), alertas de auto-monitorización → Telegram directo.

Todo orquestado como stack docker-compose: [`opt/monitoring/docker-compose.yml`](./opt/monitoring/docker-compose.yml).

## Filesystem espejado

- `opt/monitoring/` — Stack completo (compose + configs cuando se añadan).

## Notas

La estrategia de routing del Alertmanager (dual: Lobster + Telegram fallback) está documentada en [`../obsidian/wiki/06-Observabilidad`](../obsidian/wiki/06-Observabilidad).

---
title: Observabilidad — Dashboard Grafana
tags: [observabilidad, grafana, dashboard, fase7]
---

# 📊 Dashboard · Grafana

> [!abstract] Una vista de pájaro
> Archivo: `deploy/grafana/lobster-dashboard.json`. Importable directo en Grafana de Sauron. Muestra QPS, latencias, errores, modo del agente, queue Loki y backlog de aprobaciones.

## 📥 Importar

> [!example] Por UI
> 1. Grafana → Dashboards → New → Import.
> 2. "Upload JSON file" → seleccionar `deploy/grafana/lobster-dashboard.json`.
> 3. Pick the Prometheus datasource (`Sauron-Prom`).
> 4. Save.

> [!example] Por API
> ```bash
> curl -X POST https://grafana.saasphere.local/api/dashboards/db \
>   -H "Content-Type: application/json" \
>   -H "Authorization: Bearer $GRAFANA_TOKEN" \
>   --data-binary @deploy/grafana/lobster-dashboard.json
> ```

> [!example] Por provisioning
> ```yaml
> # /etc/grafana/provisioning/dashboards/lobster.yaml
> apiVersion: 1
> providers:
>   - name: lobster
>     orgId: 1
>     folder: 'SaaSphere'
>     type: file
>     options:
>       path: /var/lib/grafana/dashboards/lobster
> ```
> Luego copiar `lobster-dashboard.json` a `/var/lib/grafana/dashboards/lobster_agent/`.

## 🧱 Paneles típicos

> [!info] Lista del dashboard
> El JSON incluye, entre otros, paneles para:
> - **Uptime + version** (singlestat)
> - **Decisions/h por case_use** (timeseries apilada)
> - **Outcome ratio** (% failed)
> - **LLM latency p95 por modelo** (timeseries)
> - **Tokens consumidos** (timeseries)
> - **Errores por componente** (heatmap)
> - **HTTP requests** (table)
> - **Webhook alerts** (counter)
> - **Approvals pendientes** (gauge)
> - **Loki queue** (gauge)

→ Si abres el JSON en cualquier editor verás la lista completa de paneles con sus expresiones PromQL.

## 🎨 Convenciones de color

- Modo `normal` → verde.
- Modo `dry_run` → amarillo.
- Modo `paused` → rojo.
- Errores → rojo intenso.
- LLM latencia alta → amarillo→rojo según buckets.

## 🔗 Logs en Grafana

> [!tip] Loki como datasource
> Si Grafana tiene Loki configurado, los paneles del dashboard pueden enlazar a búsquedas como `{service="lobster"} | json | event="..."`. Esto permite saltar de "métrica alta" a "logs del momento" en un click.

→ Detalles operativos en `docs/fase_7_dashboard_grafana.md`.

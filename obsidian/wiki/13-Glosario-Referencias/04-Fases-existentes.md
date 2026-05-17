---
title: Mapa a fases existentes
tags: [glosario, fases, tfg, mapa]
---

# 🗂️ Mapa a fases existentes

> [!abstract] El árbol de archivos `obsidian/` antes de esta wiki
> Convivimos con documentos previos. Esta nota los lista y los enlaza desde la wiki, sin tocarlos.

## 📂 Archivos previos en `obsidian/`

> [!info] No editados por esta wiki
> Toda esta carpeta `obsidian/wiki/` se añadió en una rama dedicada. Los archivos de abajo se mantienen tal cual.

### Fases del TFG

```text
obsidian/TFG_Fase6_Lobster.md
obsidian/TFG_Fase7_Lobster.md
obsidian/TFG_Fase8_Lobster.md
obsidian/TFG_Fase9_Lobster.md
```

| Fase | Contenido | Equivalente en wiki |
|---|---|---|
| 6 | Scheduler autónomo + K8s watcher + webhook Alertmanager | [[../07-Scheduler-Watcher/00-MOC-Scheduler]] |
| 7 | Observabilidad (logs structlog → Loki, métricas Prom, dashboard Grafana, alertas) | [[../06-Observabilidad/00-MOC-Observabilidad]] |
| 8 | Pin/unpin de deployments entre matrix y fallback | [[../03-Tools/08-Mutations-Nodes]] |
| 9 | Cola FIFO con un único worker para serializar jobs LLM-pesados | [[../07-Scheduler-Watcher/07-Job-queue-fase9]] |

### Resúmenes diarios autogenerados

```text
obsidian/2026-05/
├── 2026-05-14_daily_summary.md
├── 2026-05-15_daily_summary.md
└── 2026-05-16_daily_summary.md
```

→ Generados por el job `daily_summary` cada 08:00. Ver [[../10-Operacion/06-Daily-summary-Obsidian]].

## 📂 Otros documentos en `docs/`

```text
docs/fase_3_cierre_validacion.md
docs/fase_4_aprobaciones.md
docs/fase_4_resumen_implementacion.md
docs/fase_7_alertas_prometheus.md
docs/fase_7_dashboard_grafana.md
docs/fase_7_metrica_errors_total.md
docs/fase_7_metrica_http_requests_total.md
```

| Documento | Equivalente en wiki |
|---|---|
| `fase_3_cierre_validacion.md` | [[../02-Agente/05-Mutation-context]] |
| `fase_4_aprobaciones.md` | [[../02-Agente/06-Approval-manager]] |
| `fase_4_resumen_implementacion.md` | [[../04-Telegram/00-MOC-Telegram]] |
| `fase_7_alertas_prometheus.md` | [[../06-Observabilidad/04-Alertas-Prometheus]] |
| `fase_7_dashboard_grafana.md` | [[../06-Observabilidad/03-Dashboard-Grafana]] |
| `fase_7_metrica_errors_total.md` | [[../06-Observabilidad/02-Metricas-Prometheus]] |
| `fase_7_metrica_http_requests_total.md` | [[../06-Observabilidad/02-Metricas-Prometheus]] |

## 🧠 Qué hace cada cosa (vista rápida)

### `TFG_Fase6_Lobster.md`

Documento académico de la Fase 6. Describe:
- Por qué se eligió APScheduler.
- Diseño del K8s watcher con reconexión exponencial.
- Webhook reactivo de Alertmanager.
- Encadenamiento `health_loop_read → health_loop_analyze`.
- Almacenamiento de `daily_summary` en Obsidian.

### `TFG_Fase7_Lobster.md`

Documento académico de la Fase 7. Cubre:
- Métricas Prometheus instrumentadas.
- Pipeline logs structlog → Loki HTTP push con batch.
- Dashboard Grafana incluido.
- 5 reglas de alerta.
- Anexos con queries y capturas.

### `TFG_Fase8_Lobster.md`

Documento académico de la Fase 8. Cubre:
- Diferencia matrix vs fallback (taints).
- Tools `pin_deployment_to_node` y `unpin_deployment_from_node`.
- Auto-generación de tolerations a partir de taints del nodo destino.
- Política de unpin estable (15 min < 70% CPU/RAM).

### `TFG_Fase9_Lobster.md`

Documento académico de la Fase 9. Cubre:
- Problema de contención GPU en homelab.
- `JobQueue` con worker único.
- Política `_DIRECT_CASE_USES` con solo `HEALTH_LOOP_READ`.
- Métricas de queue y exposición CLI/Telegram.

## 🧭 Convivencia

> [!tip] No solapamiento
> La wiki en `obsidian/wiki/` es **referencia técnica** (qué hace, cómo se opera). Los `TFG_Fase*.md` son **documentos académicos** (capturas para la memoria, narrativa). Se complementan.

> [!warning] Si actualizas las fases TFG…
> No olvides re-leer la wiki por consistencia. La wiki puede quedar desactualizada respecto a una Fase nueva. Hoy va hasta Fase 9.

→ Cierre del bloque. Vuelve al [[../00-INDEX|índice principal]] o explora el [[../12-Decisiones-Limitaciones/06-Mapa-al-TFG|Mapa al TFG]].

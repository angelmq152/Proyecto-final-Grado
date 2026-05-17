---
title: 07 · Scheduler y Watcher — MOC
tags: [moc, scheduler, apscheduler, watcher, k8s]
---

# ⏰ 07 · Scheduler y Watcher — MOC

> [!abstract] Lobster nunca duerme
> Tres mecanismos disparan al agente sin intervención humana:
> 1. **APScheduler** lanza 7 jobs periódicos (health loop cada 5 min, daily summary a las 8:00, …).
> 2. **K8s Watcher** mantiene un `watch` abierto sobre eventos Warning/CrashLoop y dispara análisis reactivos en streaming.
> 3. **Webhook** `/webhook/alert` recibe POSTs de Alertmanager y los enruta como `CaseUse.ALERT_REACTIVE`.

## Notas

- [[01-APScheduler-jobs]] — tabla completa de jobs y cron.
- [[02-Health-loop]] — los dos modos: read & analyze.
- [[03-Global-state-Summary-Daily]] — globales y resúmenes.
- [[04-Backup-Optimization]] — jobs nocturnos.
- [[05-Alert-reactive]] — reactivo a Alertmanager.
- [[06-K8s-Watcher]] — streaming de eventos.
- [[07-Job-queue-fase9]] — cola FIFO (Fase 9).

## Jobs en tabla

| Job | Intervalo / cron | CaseUse | Modelo | Think | Timeout |
|---|---|---|---|---|---|
| `health_loop` | cada 5 min | HEALTH_LOOP_READ + (opcional) HEALTH_LOOP_ANALYZE | qwen3:8b | ❌ | 300 s / 900 s |
| `global_state` | cada 30 min | GLOBAL_STATE | qwen3:8b | ✅ | 600 s |
| `hourly_summary` | cron `0 * * * *` | SUMMARY | qwen3:8b | ❌ | 600 s |
| `daily_summary` | cron `0 8 * * *` | DAILY_SUMMARY | qwen3:32b | ❌ | 1800 s |
| `backup` | cron `0 2 * * *` | BACKUP | qwen3:8b | ❌ | 300 s |
| `optimization` | cron `0 3 * * *` | OPTIMIZATION | qwen3:8b | ✅ | 600 s |
| `alert_reactive` | webhook | ALERT_REACTIVE | qwen3:8b | ❌ | 600 s |
| K8s Watcher | streaming | HEALTH_LOOP_ANALYZE | qwen3:8b | ❌ | — |

→ Detalles en cada nota individual.

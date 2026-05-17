---
title: APScheduler — jobs autónomos
tags: [scheduler, apscheduler, jobs, cron]
---

# ⏰ APScheduler · Jobs autónomos

> [!abstract] 7 jobs periódicos
> Archivo: `lobster_agent/scheduler.py`. `SchedulerRunner` envuelve `AsyncIOScheduler` de APScheduler. Cada job está protegido con `max_instances=1` y `coalesce=True` para evitar solapamientos.

## 📋 Tabla completa

| Job ID | Trigger | CaseUse | Modelo | Think | Timeout |
|---|---|---|---|---|---|
| `health_loop` | interval 5 min | HEALTH_LOOP_READ + chain ANALYZE | qwen3:8b | ❌ / ❌ | 300 s / 900 s |
| `global_state` | interval 30 min | GLOBAL_STATE | qwen3:8b | ✅ | 600 s |
| `hourly_summary` | cron `0 * * * *` | SUMMARY | qwen3:8b | ❌ | 600 s |
| `daily_summary` | cron `0 8 * * *` | DAILY_SUMMARY | qwen3:32b | ❌ | 1800 s |
| `backup` | cron `0 2 * * *` | BACKUP | qwen3:8b | ❌ | 300 s |
| `optimization` | cron `0 3 * * *` | OPTIMIZATION | qwen3:8b | ✅ | 600 s |
| `alert_reactive` | webhook | ALERT_REACTIVE | qwen3:8b | ❌ | 600 s |

## 🚀 Arranque

```python
def start(self):
    self._scheduler.add_job(self._health_loop_job, IntervalTrigger(minutes=5), id="health_loop", ...)
    self._scheduler.add_job(self._global_state_job, IntervalTrigger(minutes=30), id="global_state", ...)
    if self._config.hourly_summary_enabled:
        self._scheduler.add_job(self._hourly_summary_job, CronTrigger(minute=0), id="hourly_summary", ...)
    self._scheduler.add_job(self._daily_summary_job, CronTrigger(hour=8, minute=0), id="daily_summary", ...)
    self._scheduler.add_job(self._backup_job, CronTrigger(hour=2), id="backup", ...)
    self._scheduler.add_job(self._optimization_job, CronTrigger(hour=3), id="optimization", ...)
    self._scheduler.start()
```

## 🛡️ Anti-solapamiento

```python
add_job(... , max_instances=1, coalesce=True, replace_existing=True)
```

- `max_instances=1` → si un job sigue corriendo cuando llega el siguiente trigger, el nuevo se descarta.
- `coalesce=True` → si dos triggers se acumulan (sistema parado), se ejecuta solo uno.
- `replace_existing=True` → permite reiniciar Lobster sin duplicar jobs.

## 🔧 Configuración

```python
class SchedulerConfig(BaseModel):
    timezone: str = "Europe/Madrid"
    health_loop_interval_minutes: int = 5
    global_state_interval_minutes: int = 30
    hourly_summary_enabled: bool = True
    daily_summary_hour: int = 8
    daily_summary_minute: int = 0
    backup_hour: int = 2
    backup_minute: int = 0
    optimization_hour: int = 3
    optimization_minute: int = 0
    k8s_watcher_enabled: bool = True
    k8s_watcher_reconnect_delay_seconds: float = 5.0
    k8s_watcher_max_reconnect_delay_seconds: float = 120.0
    obsidian_path: str = "/opt/lobster/obsidian"
    node_pressure_cpu_threshold_pct: float = 85.0
    node_pressure_memory_threshold_pct: float = 85.0
    node_pressure_unpin_cpu_threshold_pct: float = 70.0
    node_pressure_unpin_memory_threshold_pct: float = 70.0
    node_pressure_unpin_stable_minutes: int = 15
```

## 🧪 `_run_scheduled_job` — el patrón común

Todos los jobs caen en este método:

```python
async def _run_scheduled_job(self, case_use, prompt, *, notify, follow_up_on_anomaly=False, save_obsidian=False, job_timeout=600):
    try:
        result = await asyncio.wait_for(self._agent.run(case_use, prompt), timeout=job_timeout)
        lobster_last_cycle_timestamp.labels(case_use=case_use.value).set(time.time())
        lobster_scheduler_runs_total.labels(case_use=case_use.value, outcome=result.outcome).inc()
        if result.outcome == "success" and result.data:
            if notify:
                # Mensaje Telegram con header emoji + body MarkdownV2
                ...
            if save_obsidian:
                # _save_obsidian_note para daily_summary
                ...
            if follow_up_on_anomaly and _has_anomaly(result.data):
                await self._run_analyze_phase(result.data)
        elif result.outcome == "failed":
            log.warning(...)
    except TimeoutError:
        lobster_scheduler_runs_total.labels(outcome="timeout").inc()
    except Exception:
        lobster_scheduler_runs_total.labels(outcome="exception").inc()
        if self._session_reset_fn:
            await self._session_reset_fn()       # SQLAlchemy session rollback
```

## 📊 Métricas emitidas por job

| Métrica | Cuándo |
|---|---|
| `lobster_last_cycle_timestamp{case_use}` | Cada éxito |
| `lobster_scheduler_runs_total{case_use, outcome}` | Cada finalización |
| `lobster_errors_total{component="scheduler"}` | timeout o exception |

→ Detalles por job en las siguientes notas.

---
title: Job queue — Fase 9
tags: [scheduler, job-queue, fifo, fase9, ollama]
---

# 🧵 Job queue · Fase 9

> [!abstract] Serializar para no pelearse con Ollama
> La **Fase 9** introdujo una cola FIFO con un único worker para todos los jobs **excepto** `health_loop_read`. Razón: la GPU del homelab no tiene VRAM para 8b y 32b cargados a la vez — cada switch cuesta ~8 s. Sin cola, los jobs solapados generaban thrashing.

## 🚪 Quién entra a la cola

| Job | Modo |
|---|---|
| `health_loop_read` | **Directo** (rápido y crítico) |
| `health_loop_analyze` | Cola |
| `alert_reactive` | Cola |
| `hourly_summary` | Cola |
| `global_state` | Cola |
| `backup` | Cola |
| `optimization` | Cola |
| `daily_summary` | Cola |

```python
_DIRECT_CASE_USES: frozenset[CaseUse] = frozenset({CaseUse.HEALTH_LOOP_READ})
```

## 🧵 `JobQueue`

```python
class JobQueue:
    def __init__(self, maxsize=20):
        self._queue: asyncio.Queue[QueuedJob] = asyncio.Queue(maxsize=maxsize)
        self._running: QueuedJob | None = None
        self._worker_task: asyncio.Task | None = None
```

- `start()` → arranca el worker.
- `enqueue(job)` → `bool` (False si llena, política de drop con warning).
- `running` → `QueuedJob | None`.
- `pending_count` → `int`.
- `pending_jobs()` → `list[QueuedJob]`.
- `stop()` → cancela el worker.

## 🧪 Worker

```python
async def _worker(self):
    while True:
        job = await self._queue.get()
        self._running = job
        wait_s = time.monotonic() - job.enqueued_at
        lobster_queue_wait_seconds.observe(wait_s)
        try:
            await job.run_fn()
        except Exception:
            log.exception("lobster.queue.job_failed", ...)
        finally:
            self._running = None
```

> [!info] `time.monotonic()` y no `time.time()`
> El cómputo de tiempo de espera usa `monotonic()` para ser inmune a saltos del reloj del sistema (NTP, hibernación).

## 🚏 Bifurcación en `_run_scheduled_job`

```python
async def _run_scheduled_job(self, case_use, prompt, *, notify, ...):
    if case_use in _DIRECT_CASE_USES:
        await self._execute_job(case_use, prompt, notify=notify, ...)
    else:
        async def _run():
            await self._execute_job(case_use, prompt, notify=notify, ...)
        enqueued = self._job_queue.enqueue(
            QueuedJob(case_use=case_use, prompt=prompt, run_fn=_run)
        )
        if not enqueued:
            log.warning("lobster.scheduler.job.dropped", case_use=case_use.value)
```

## 🚨 Política de overflow

> [!warning] Drop, no block
> Si la cola está llena (20 jobs), `enqueue` retorna `False` y el job nuevo **se descarta** con un warning. Razón: bloquear bloquearía a APScheduler y la siguiente iteración del trigger. Mejor perder un job que perder el bucle entero.

## 📊 Métricas Fase 9

- `lobster_queue_pending` — gauge con `pending_count`.
- `lobster_queue_wait_seconds` — histogram de espera por job.
- `lobster_queue_running` — gauge 0/1 según si hay job corriendo.

## 📋 Inspección

```bash
# CLI
uv run lobster queue list
# → [ "daily_summary (running)", "alert_reactive (pending, 1)", "optimization (pending, 2)" ]

# Telegram
/queue
🧵 Lobster queue:
- ⚡ daily_summary (corriendo, 4 min)
- 🕓 alert_reactive (pending #1)
```

## 🏗️ Por qué no priorización

> [!tip] Sencillez sobre sofisticación
> La cola es **FIFO pura** — no prioriza alert_reactive sobre daily_summary aunque sea más urgente. Razón: meter prioridades habría requerido considerar starvation, fairness, etc. En la práctica:
> - `health_loop_read` corre directo (no espera).
> - El watcher dispara directo a `_agent.run` (no pasa por la cola).
> - La latencia añadida por la cola raramente excede 10 min.
>
> Si se demuestra que sí pasa, el roadmap incluye `PriorityJobQueue`.

→ Documento académico completo en `obsidian/TFG_Fase9_Lobster.md`.

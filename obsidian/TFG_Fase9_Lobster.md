# Fase 9 — Cola de la IA (serialización de jobs pesados)

## ¿Qué es la Fase 9?

> [!abstract] Resumen ejecutivo
> La Fase 9 introduce una **cola FIFO serializada** para los jobs del scheduler que invocan al LLM. Hasta esta fase, todos los jobs (health check, daily summary, backup, alertas reactivas, etc.) podían ejecutarse en paralelo. Esto generaba contención en Ollama porque la GPU del homelab no tiene VRAM suficiente para mantener cargados simultáneamente `qwen3:8b` y `qwen3:32b`: cada cambio de modelo implicaba carga/descarga (~8 s) y serialización interna en Ollama.
>
> Con esta fase, los jobs pesados se procesan **de uno en uno** a través de un worker único. El único job que mantiene ejecución directa (sin pasar por la cola) es `health_loop_read`, porque dura <30 segundos y es crítico para la seguridad del clúster. Los jobs en cola son inspeccionables desde Telegram con `/queue` y desde la CLI con `lobster queue list`.

> [!note] Tecnologías utilizadas
> `asyncio.Queue` · `asyncio.Task` · `APScheduler` · `aiogram` · `Typer` · `httpx` · `prometheus_client` · `FastAPI` · `structlog`

---

## Lo que está implementado (rama `worktree-fase-9-job-queue`)

### 1. Nuevo módulo `lobster_agent/job_queue.py`

> [!tip] Explicación para el TFG
> El módulo central de la fase. Define dos clases: `QueuedJob` (un dataclass que encapsula un job a ejecutar) y `JobQueue` (la cola propiamente, con un único worker asíncrono). La cola usa `asyncio.Queue(maxsize=20)` internamente y un `asyncio.Task` que consume los jobs uno a uno. Si la cola está llena, el job nuevo se descarta con un warning (política de drop, no de blocking). El tiempo de espera se mide con `time.monotonic()` para ser inmune a saltos del reloj del sistema.

> [!example] API pública de `JobQueue`
> ```python
> queue = JobQueue()
> queue.start()                            # arranca el worker
> queue.enqueue(QueuedJob(...))            # → bool (False si llena)
> queue.running                            # → QueuedJob | None
> queue.pending_count                      # → int
> queue.pending_jobs()                     # → list[QueuedJob]
> await queue.stop()                       # cancela el worker
> ```

> [!example] Estructura del worker
> ```python
> async def _worker(self):
>     while True:
>         job = await self._queue.get()
>         self._running = job
>         wait_s = time.monotonic() - job.enqueued_at
>         lobster_queue_wait_seconds.observe(wait_s)
>         try:
>             await job.run_fn()
>         except Exception:
>             log.exception(...)
>         finally:
>             self._running = None
> ```

---

### 2. Clasificación de jobs en `lobster_agent/scheduler.py`

> [!tip] Explicación para el TFG
> La regla de clasificación es deliberadamente sencilla: un job va a la cola **salvo que** dure menos de 30 segundos y sea crítico para la seguridad del clúster. Solo `health_loop_read` cumple ambas condiciones. El resto, incluido `alert_reactive`, va a la cola para evitar que ráfagas de alertas de Alertmanager (típicas durante un incidente) se solapen entre sí o pisen a otros jobs.

> [!example] Constante en `scheduler.py`
> ```python
> # Solo health_loop_read corre de forma directa (lectura rápida, <30 s, crítica).
> # Todo lo demás pasa por la cola para evitar contención en Ollama.
> _DIRECT_CASE_USES: frozenset[CaseUse] = frozenset({CaseUse.HEALTH_LOOP_READ})
> ```

> [!example] Tabla completa de clasificación
> | Job | Modelo | Duración típica | Modo |
> |---|---|---|---|
> | `health_loop_read` | qwen3:8b | 15-30 s | **Directo** |
> | `health_loop_analyze` | qwen3:8b + think | 1-3 min | Cola |
> | `alert_reactive` | qwen3:8b + think | 1-2 min | Cola |
> | `hourly_summary` | qwen3:8b | 1-2 min | Cola |
> | `global_state` | qwen3:8b + think | 2-4 min | Cola |
> | `backup` | qwen3:8b | 1-3 min | Cola |
> | `optimization` | qwen3:8b + think | 2-5 min | Cola |
> | `daily_summary` | qwen3:32b | 8-12 min | Cola |

---

### 3. Bifurcación en `_run_scheduled_job()`

> [!tip] Explicación para el TFG
> El método `_run_scheduled_job` de `SchedulerRunner` es el punto donde cada trigger de APScheduler entra en el sistema. Tras la Fase 9, decide en tiempo de ejecución si el job debe correr directamente o pasar por la cola. La ejecución directa llama a `_execute_job` (la lógica antigua), mientras que la versión encolada envuelve la misma lógica en una coroutine `_run` que se entrega a `JobQueue.enqueue`.

> [!example] Lógica de bifurcación
> ```python
> async def _run_scheduled_job(self, case_use, prompt, *, notify, ...):
>     if case_use in _DIRECT_CASE_USES:
>         await self._execute_job(case_use, prompt, notify=notify, ...)
>     else:
>         async def _run() -> None:
>             await self._execute_job(case_use, prompt, notify=notify, ...)
>
>         enqueued = self._job_queue.enqueue(
>             QueuedJob(case_use=case_use, prompt=prompt, run_fn=_run)
>         )
>         if not enqueued:
>             log.warning("lobster.scheduler.job.dropped", case_use=case_use.value)
> ```

---

### 4. `_run_analyze_phase` pasa a síncrono

> [!tip] Explicación para el TFG
> Antes de la Fase 9, cuando el `health_loop_read` detectaba una anomalía, llamaba a `await self._run_analyze_phase(...)` que ejecutaba el análisis con `qwen3:8b + think` y esperaba a que terminase. Esto bloqueaba al health loop durante 1-3 minutos. Tras la Fase 9, el método deja de ser `async`: simplemente encola la fase de análisis en `JobQueue` y devuelve inmediatamente. El análisis se ejecutará cuando le toque turno en la cola, sin bloquear al health loop, que puede seguir disparándose cada 5 minutos.

> [!example] Cambio en `_run_analyze_phase`
> ```python
> def _run_analyze_phase(self, read_output: str) -> None:
>     prompt = f"{_HEALTH_LOOP_ANALYZE_PROMPT}\n\nResumen…\n{read_output[:2000]}"
>
>     async def _analyze() -> None:
>         try:
>             result = await asyncio.wait_for(
>                 self._agent.run(CaseUse.HEALTH_LOOP_ANALYZE, prompt),
>                 timeout=900,
>             )
>             # … emite métricas y envía resumen a Telegram
>         except TimeoutError: ...
>         except Exception: ...
>
>     self._job_queue.enqueue(
>         QueuedJob(case_use=CaseUse.HEALTH_LOOP_ANALYZE, prompt=prompt, run_fn=_analyze)
>     )
> ```

---

### 5. Dos métricas nuevas en `lobster_agent/observability/metrics.py`

> [!tip] Explicación para el TFG
> Se exponen dos métricas Prometheus específicas de la cola. `lobster_queue_depth` es un *gauge* que indica cuántos jobs hay esperando en cada momento; en operación normal debería estar casi siempre en 0 o 1. `lobster_queue_wait_seconds` es un *histogram* que mide cuánto esperó cada job desde que se encoló hasta que empezó a ejecutarse. Los buckets están diseñados para cubrir desde 1 segundo hasta 30 minutos, cubriendo el caso peor (un job esperando a que termine el `daily_summary`).

> [!example] Métricas añadidas
> ```python
> lobster_queue_depth = Gauge(
>     "lobster_queue_depth",
>     "Number of jobs currently waiting in the AI job queue",
> )
> lobster_queue_wait_seconds = Histogram(
>     "lobster_queue_wait_seconds",
>     "Time a job spent waiting in the queue before execution",
>     buckets=[1, 5, 15, 30, 60, 120, 300, 600, 900, 1800],
> )
> ```

---

### 6. Endpoint HTTP `GET /admin/queue`

> [!tip] Explicación para el TFG
> Como la cola es in-memory (vive en el proceso del servidor), no hay forma de inspeccionarla desde fuera salvo a través de una API. Se añadió un endpoint admin que devuelve el estado actual: qué se está ejecutando y qué hay pendiente. Este endpoint lo consume la CLI (`lobster queue list`) y podría consumirlo cualquier dashboard externo.

> [!example] Respuesta del endpoint
> ```json
> {
>   "running": "daily_summary",
>   "pending_count": 2,
>   "pending": ["backup", "alert_reactive"]
> }
> ```

---

### 7. Comando `/queue` en Telegram

> [!tip] Explicación para el TFG
> Se añadió un nuevo handler a `lobster_agent/telegram/handlers.py` que muestra el estado de la cola en formato humano. La inyección de dependencias usa el mismo patrón que el resto de handlers de aiogram v3: el `JobQueue` se pasa al `Dispatcher` como keyword argument y aiogram lo inyecta automáticamente a cualquier handler que tenga `job_queue: JobQueue` en su firma.

> [!example] Ejemplo de respuesta del comando
> ```
> ⚙️ Ejecutando: daily_summary
>
> 📋 Pendientes (2):
>   1. backup
>   2. alert_reactive
> ```
>
> Si nada corre y la cola está vacía:
> ```
> ⚙️ Sin job activo en cola
>
> 📋 Cola vacía
> ```

---

### 8. Subcomando `lobster queue list` en la CLI

> [!tip] Explicación para el TFG
> La CLI ya tenía subcomandos para inspeccionar la BD (`decisions list`, `actions list`, etc.), pero la cola vive en memoria del proceso servidor, no en BD. Por tanto, el nuevo subcomando es el primer caso en la CLI que hace una llamada HTTP al servidor (vía `httpx`). Requiere que el servidor esté corriendo.

> [!example] Uso desde terminal
> ```bash
> uv run lobster queue list
> uv run lobster queue list --host localhost --port 8080
> ```
>
> Salida (mismo contenido que `/queue` pero en texto plano):
> ```
> ⚙️  Ejecutando: daily_summary
> 📋 Pendientes (1):
>   1. backup
> ```

---

## Diagrama de flujo de la Fase 9

```
                APScheduler trigger
                        │
                        ▼
                ┌───────────────┐
                │ case_use en   │
                │ _DIRECT_CASE_ │  ── Sí ──► LobsterAgent.run() ──► Ollama
                │   USES?       │           (sin pasar por cola)
                └───────────────┘
                        │
                        No
                        ▼
                ┌───────────────┐
                │  JobQueue.    │
                │  enqueue()    │
                └───────────────┘
                        │
                        ▼
        ╔═══════════════════════════════╗
        ║   asyncio.Queue (maxsize=20)  ║
        ║                               ║
        ║   [job1] [job2] [job3]…       ║
        ╚═══════════════════════════════╝
                        │
                        ▼
                ┌───────────────┐
                │   worker      │   ← una sola asyncio.Task
                │   (uno a uno) │
                └───────────────┘
                        │
                        ▼
                LobsterAgent.run()
                        │
                        ▼
                      Ollama
```

---

## Ficheros modificados / creados

| Fichero | Estado | Qué cambió |
|---|---|---|
| `lobster_agent/job_queue.py` | **Creado** | Clases `QueuedJob` y `JobQueue`, worker único asyncio |
| `lobster_agent/observability/metrics.py` | Modificado | +`lobster_queue_depth`, +`lobster_queue_wait_seconds` |
| `lobster_agent/scheduler.py` | Modificado | +`_DIRECT_CASE_USES`, bifurcación en `_run_scheduled_job`, `_run_analyze_phase` síncrono |
| `lobster_agent/main.py` | Modificado | Crea `JobQueue`, lo wire al scheduler y al bot, expone `GET /admin/queue` |
| `lobster_agent/telegram/bot.py` | Modificado | Acepta `job_queue` y lo inyecta al Dispatcher |
| `lobster_agent/telegram/handlers.py` | Modificado | +comando `/queue` |
| `lobster_agent/cli.py` | Modificado | +subcomando `queue list` (httpx contra `/admin/queue`) |
| `docs/fase_9_cola_ia.md` | **Creado** | Resumen de implementación |
| `codex/fase_9_lobster_cola_de_la_ia.md` | **Creado** | Documento de diseño y razonamiento |

---

## Lo que queda por hacer

> [!warning] Pendiente de despliegue y validación
> El código está completo en la rama `worktree-fase-9-job-queue` y ha pasado las comprobaciones de importación y de lint. **No se ha probado en runtime** porque había un modelo en pruebas en el momento de la implementación. La verificación funcional queda como siguiente paso.

> [!todo] Checklist de despliegue
> - [ ] **Mergear la rama a main**
>   ```bash
>   git merge worktree-fase-9-job-queue
>   ```
> - [ ] **Reiniciar el servicio Lobster** en LeIA
>   ```bash
>   sudo systemctl restart lobster
>   ```
> - [ ] **Verificar que la cola arranca vacía**
>   ```bash
>   uv run lobster queue list
>   ```
> - [ ] **Disparar un daily_summary manualmente** y comprobar que aparece como "Ejecutando"
>   ```bash
>   curl -X POST http://localhost:8080/admin/trigger/daily_summary
>   uv run lobster queue list
>   ```
> - [ ] **Disparar un segundo job** mientras corre el daily, y verificar que aparece en "Pendientes"
>   ```bash
>   curl -X POST http://localhost:8080/admin/trigger/backup
>   uv run lobster queue list
>   ```
> - [ ] **Verificar que `/queue` en Telegram** devuelve la misma información
> - [ ] **Comprobar las métricas Prometheus**
>   ```bash
>   curl -s http://localhost:8080/metrics | grep lobster_queue
>   ```
> - [ ] **Validar que `health_loop_read` sigue ejecutándose cada 5 min** aunque haya un daily_summary corriendo
>   ```bash
>   journalctl -u lobster -f | grep health_loop
>   ```

---

## Decisiones de diseño

| Decisión | Alternativa descartada | Razón |
|---|---|---|
| Cola FIFO explícita | `asyncio.Semaphore(1)` | El semáforo es opaco: no permite ver qué hay esperando. La cola explícita habilita `/queue` y `queue list` |
| Worker único (concurrencia = 1) | Worker con N concurrencia | N > 1 reintroduce el problema de fondo: varios modelos compitiendo por VRAM en Ollama |
| Cola in-memory (efímera) | Persistencia en SQLite | Serializar coroutines no es trivial, y APScheduler ya redispara los cron jobs si se pierden |
| Política de **drop** al estar llena | Bloqueo/backpressure | 20 pendientes ya implica un problema serio; apilar más solo lo agrava |
| `alert_reactive` va a la cola | Bypass directo | Alertmanager puede disparar ráfagas durante incidentes; en cola se procesan en orden sin pisarse |
| `health_loop_analyze` va a la cola | Ejecución bloqueante tras `read` | El read no debe quedar bloqueado por el análisis; el análisis espera su turno |
| Solo `health_loop_read` es directo | Más jobs directos | Es el único que cumple "<30 s + crítico para seguridad" |
| `time.monotonic()` para wait_seconds | `datetime.now()` | Inmune a saltos de reloj (NTP, DST) — lo correcto para medir intervalos |
| Maxsize = 20 hardcoded | Configurable por env | YAGNI: en operación normal nunca se llega a 5 pendientes; cuando se llegue, se hace configurable |
| Inyección de `JobQueue` al Dispatcher de aiogram | Singleton global | Mantiene el patrón de DI ya usado por `approval_manager`, `notifier`, `agent` |

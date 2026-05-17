# Fase 7 — Observabilidad Completa

## ¿Qué es la Fase 7?

> [!abstract] Resumen ejecutivo
> La Fase 7 hace que Lobster sea completamente observable. Hasta ahora el agente actuaba, pero era opaco: sabías que algo había pasado por los logs, pero no podías cuantificarlo ni alertar sobre ello de forma sistemática. Con esta fase, Lobster expone **12 métricas Prometheus** sobre su propio comportamiento interno, tiene un **dashboard Grafana dedicado** con 17 paneles, y genera **9 reglas de alerta** que avisan cuando el agente falla, se bloquea o degrada.
>
> El principio que guía esta fase es simple: **el monitor debe ser monitorizable**. Un agente autónomo que nadie puede observar es un riesgo operativo; un agente observable es un sistema de confianza.

> [!note] Tecnologías utilizadas
> `prometheus-client` · `Prometheus 2.55` · `Grafana 11.3` · `Loki 3.2` · `structlog` · `FastAPI middleware` · `Alertmanager 0.27` · `Docker Compose (Sauron)`

---

## Demostraciones

---

### 1. Endpoint `/metrics` con las 12 métricas instrumentadas

> [!tip] Explicación para el TFG
> Lobster expone sus métricas en el estándar de Prometheus. Cualquier sistema compatible puede rascarlas cada 15 segundos y almacenar el historial. Las métricas cubren cuatro dimensiones: **actividad del agente** (decisiones, latencia, tokens), **errores internos** (por componente y severidad), **operaciones externas** (requests HTTP recibidos, alertas de Alertmanager, jobs del scheduler) y **estado de recursos auxiliares** (cola de Loki, aprobaciones pendientes).

> [!example] Comando para la captura
> ```bash
> curl -s http://localhost:8080/metrics | grep '^lobster_' | grep -v '^#'
> ```

---

### 2. Métrica `lobster_decisions_total` — actividad del LLM

> [!tip] Explicación para el TFG
> Cada vez que el agente completa un ciclo de inferencia, esta métrica se incrementa. Está desglosada por `case_use` (qué tarea), `model` (qwen3:8b o qwen3:32b), `think` (modo razonamiento activado o no) y `outcome` (success / failed / skipped_paused). Con esto se puede ver en Grafana cuántas decisiones toma el sistema por minuto, y si empiezan a fallar.

> [!example] Consulta PromQL para Grafana
> ```promql
> sum(rate(lobster_decisions_total[5m])) by (case_use, outcome)
> ```

> [!example] Verificación desde la terminal de LeIA
> ```bash
> curl -s http://localhost:8080/metrics | grep 'lobster_decisions_total{' | head -10
> ```

---

### 3. Métrica `lobster_llm_latency_seconds` — latencia del LLM

> [!tip] Explicación para el TFG
> Esta métrica es un **Histogram**: no guarda un solo valor sino la distribución completa de latencias. Permite calcular percentiles reales (p50, p95, p99) por modelo. Es especialmente relevante para `qwen3:32b`, que puede tardar varios minutos en modo think. La alerta `LobsterLatenciaLLMAlta` salta si el p95 supera los 5 minutos durante 10 minutos seguidos.

> [!example] Consulta para ver latencia p95 en tiempo real
> ```promql
> histogram_quantile(0.95,
>   sum(rate(lobster_llm_latency_seconds_bucket[10m])) by (le, model)
> )
> ```

---

### 4. Métrica `lobster_errors_total` — excepciones internas

> [!tip] Explicación para el TFG
> Antes de esta fase, los errores del agente eran invisibles salvo en los logs. Ahora cada excepción no controlada incrementa un contador etiquetado por `component` (agent, scheduler, k8s_watcher) y `severity` (error, warning). Esto permite detectar si un componente concreto está degradado antes de que el sistema entero falle.

> [!example] Consulta — tasa de errores por componente
> ```promql
> sum(rate(lobster_errors_total{severity="error"}[5m])) by (component)
> ```

> [!example] Verificar desde terminal
> ```bash
> curl -s http://localhost:8080/metrics | grep lobster_errors_total
> ```

---

### 5. Métrica `lobster_approvals_pending` — aprobaciones bloqueadas

> [!tip] Explicación para el TFG
> Cuando el agente solicita una acción que requiere confirmación humana (como borrar un tenant o escalar un deployment), la aprobación queda en cola. Esta Gauge refleja cuántas hay en estado `PENDING` en cada momento. Si se acumulan más de 5 durante 30 minutos, salta la alerta `LobsterAprobacionesAcumuladas`: significa que el operador no está respondiendo y el agente está bloqueado.

> [!example] Ver el valor actual
> ```bash
> curl -s http://localhost:8080/metrics | grep lobster_approvals_pending
> ```

> [!example] Ver aprobaciones reales en la base de datos
> ```bash
> uv run lobster approvals list
> ```

---

### 6. Métrica `lobster_loki_queue_size` — salud del pipeline de logs

> [!tip] Explicación para el TFG
> Los logs de Lobster se envían a Loki de forma asíncrona: se encolan en memoria y se vacían cada 5 segundos en batches. Esta Gauge mide cuántas entradas hay en la cola en cada momento (máximo 1000). Si la cola supera las 800 entradas durante 5 minutos, salta `LobsterLokiQueueLlena`: Loki no está respondiendo y hay riesgo de perder logs.

> [!example] Ver el estado de la cola
> ```bash
> curl -s http://localhost:8080/metrics | grep lobster_loki_queue_size
> ```

---

### 7. Middleware HTTP — `lobster_http_requests_total`

> [!tip] Explicación para el TFG
> Todo el tráfico HTTP que recibe Lobster queda registrado: las peticiones a `/health` del healthcheck de systemd, las del scrape de Prometheus a `/metrics`, y las alertas de Alertmanager a `/webhook/alert`. Cada request se cuenta por `endpoint` y `status`. Esto permite detectar si el webhook de alertas deja de recibir llamadas, o si el healthcheck empieza a devolver errores 5xx.

> [!example] Ver el volumen de webhooks recibidos en la última hora
> ```promql
> increase(lobster_http_requests_total{endpoint="/webhook/alert",status="202"}[1h])
> ```

---

### 8. Dashboard Grafana — 17 paneles en 5 filas

> [!tip] Explicación para el TFG
> El dashboard está organizado en cinco secciones lógicas que responden a las preguntas clave del operador: *¿Está vivo el agente?* (fila 1), *¿Cuántas decisiones toma y con qué resultado?* (fila 2), *¿Qué latencia y cuántos tokens consume el LLM?* (fila 3), *¿Los jobs del scheduler corren bien?* (fila 4), *¿Cuántas alertas llegan por webhook?* (fila 5). El JSON del dashboard está versionado en el repositorio y se carga por provisioning automático.

> [!success] URL en Sauron
> ```
> http://sauron:3000/d/lobster-obs-v1/lobster-e28094-observabilidad
> ```

> [!example] Captura recomendada para el TFG
> Abrir el dashboard con el rango temporal en **Last 3 hours** durante un health loop activo. Deben verse picos en `lobster_decisions_total` cada 5 minutos y la latencia del p95 de `qwen3:8b` por debajo de los 60 segundos.

---

### 9. Las 9 reglas de alerta en Prometheus

> [!tip] Explicación para el TFG
> Las reglas de alerta están definidas en `deploy/prometheus/lobster.rules.yaml` y cargadas automáticamente en Prometheus de Sauron. Cubren los fallos más importantes: proceso caído, health loop estancado, errores internos elevados, latencia del LLM disparada, demasiadas aprobaciones sin resolver, scheduler fallando, cola de Loki llena y reinicios inesperados.

> [!example] Ver las alertas cargadas en Prometheus
> ```bash
> curl -s http://sauron:9090/api/v1/rules | python3 -c \
>   "import json,sys; rules=json.load(sys.stdin);
>   [print(r['name'], '-', r['state'])
>    for g in rules['data']['groups']
>    for r in g['rules']
>    if g['name']=='lobster']"
> ```

> [!example] Probar la alerta `LobsterSinActividad`
> ```bash
> # 1. Pausar el agente (para que deje de actualizar lobster_last_cycle_timestamp)
> uv run lobster state set paused
>
> # 2. Esperar ~15 min y verificar en Prometheus UI
> # http://sauron:9090/alerts → LobsterDecisionesEstancadas debería pasar a "pending"
>
> # 3. Reanudar
> uv run lobster state set normal
> ```

---

### 10. Alerta `LobsterRestart` — proceso reiniciado

> [!tip] Explicación para el TFG
> Esta alerta es sutil pero valiosa: dispara de forma inmediata (sin `for`) si `lobster_uptime_seconds` baja de 120 segundos. Como el uptime se reinicia con el proceso, cualquier caída y reinicio queda registrado aunque nadie esté mirando. En la defensa se puede mostrar cómo Alertmanager envía esta alerta a Telegram, cerrando el bucle de observabilidad.

> [!example] Simular el reinicio para la demo
> ```bash
> sudo systemctl restart lobster
> # Esperar ~30s y abrir Grafana — el panel "Uptime" mostrará el contador desde cero
> ```

---

### 11. Logs estructurados en Loki con campos consistentes

> [!tip] Explicación para el TFG
> Todos los logs de Lobster siguen el formato JSON de structlog y se envían a Loki con el label `service=lobster`. Cada línea de log incluye campos como `case_use`, `model`, `decision_id`, `latency_ms` u `outcome`, lo que permite hacer filtros precisos en Grafana (Explore → Loki). Esto es lo que diferencia a un sistema observable de uno que solo "tiene logs".

> [!example] Filtro en Loki para ver decisiones completadas
> ```logql
> {service="lobster"} |= "decision.completed" | json | line_format "{{.case_use}} {{.outcome}} {{.latency_ms}}ms"
> ```

> [!example] Filtrar solo excepciones
> ```logql
> {service="lobster"} |= "exception"
> ```

---

## Catálogo de métricas

| Métrica | Tipo | Labels principales | Qué mide |
|---|---|---|---|
| `lobster_info` | Gauge | `version` | Siempre 1; lleva la versión desplegada |
| `lobster_uptime_seconds` | Gauge | — | Segundos desde el último arranque |
| `lobster_decisions_total` | Counter | `case_use`, `model`, `think`, `outcome` | Ciclos de inferencia LLM completados |
| `lobster_llm_latency_seconds` | Histogram | `case_use`, `model` | Duración end-to-end de cada llamada al LLM |
| `lobster_llm_tokens_total` | Counter | `case_use`, `model`, `direction` | Tokens consumidos (input / output) |
| `lobster_scheduler_runs_total` | Counter | `case_use`, `outcome` | Ejecuciones de jobs programados |
| `lobster_last_cycle_timestamp` | Gauge | `case_use` | Timestamp Unix del último job por tipo |
| `lobster_webhook_alerts_total` | Counter | `status` | Alertas recibidas de Alertmanager |
| `lobster_http_requests_total` | Counter | `endpoint`, `status` | Peticiones HTTP servidas por FastAPI |
| `lobster_errors_total` | Counter | `component`, `severity` | Excepciones no controladas por componente |
| `lobster_approvals_pending` | Gauge | — | Aprobaciones humanas en estado PENDING |
| `lobster_loki_queue_size` | Gauge | — | Entradas en cola de push a Loki |

---

## Catálogo de alertas

| Alerta | Severidad | Condición resumida |
|---|---|---|
| `LobsterSinActividad` | critical | `up{job="lobster"} == 0` durante 5 min |
| `LobsterDecisionesEstancadas` | warning | Health loop sin ciclo en > 15 min |
| `LobsterDecisionesFallidas` | warning | > 20% de decisiones fallando en 15 min |
| `LobsterTasaErroresAlta` | warning | > 0.05 errores/s (exceptions) durante 3 min |
| `LobsterLatenciaLLMAlta` | warning | p95 latencia > 5 min durante 10 min |
| `LobsterAprobacionesAcumuladas` | warning | > 5 aprobaciones pendientes durante 30 min |
| `LobsterSchedulerFallando` | warning | Jobs con outcome=failed/exception en 15 min |
| `LobsterLokiQueueLlena` | warning | Cola Loki > 800 entradas durante 5 min |
| `LobsterRestart` | info | Uptime < 120s (reinicio detectado) |

---

## Diagrama de observabilidad

```
Lobster (LeIA :8080)
        │
        ├─► /metrics ◄──── Prometheus (Sauron) ────► Alertmanager
        │   (12 métricas)          │                      │
        │                    Grafana Dashboard         Telegram
        │                    (17 paneles)              Admin
        │
        ├─► structlog ──► Loki (Sauron) ────────────► Grafana Explore
        │   (JSON)        {service="lobster"}
        │
        └─► /health ◄──── systemd healthcheck
            (uptime)      (cada 30s)

Prometheus rules → 9 alertas → Alertmanager → Telegram Admin
                                             └► /webhook/alert (Lobster)
```

---

## Ficheros relevantes del repositorio

| Fichero | Descripción |
|---|---|
| `lobster_agent/observability/metrics.py` | Declaración de las 12 métricas |
| `lobster_agent/observability/logging.py` | Pipeline structlog → cola → Loki |
| `lobster_agent/agent/orchestrator.py` | Instrumentación de decisiones y errores LLM |
| `lobster_agent/scheduler.py` | Instrumentación de jobs y errores del scheduler |
| `lobster_agent/k8s_watcher.py` | Instrumentación de reconexiones y errores del watcher |
| `lobster_agent/agent/approvals.py` | Actualización de `lobster_approvals_pending` |
| `lobster_agent/main.py` | Middleware HTTP para `lobster_http_requests_total` |
| `deploy/prometheus/lobster.rules.yaml` | 9 reglas de alerta (en Sauron) |
| `deploy/grafana/lobster-dashboard.json` | Dashboard Grafana (en Sauron, provisioning) |
| `docs/fase_7_alertas_prometheus.md` | Guía de instalación en Sauron |
| `docs/fase_7_dashboard_grafana.md` | Guía de importación del dashboard |

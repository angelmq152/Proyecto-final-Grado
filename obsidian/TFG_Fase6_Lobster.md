# Fase 6 — Triggers Autónomos, Scheduler y Watcher

## ¿Qué es la Fase 6?

> [!abstract] Resumen ejecutivo
> La Fase 6 convierte a Lobster en un agente verdaderamente autónomo. Hasta esta fase, el sistema solo respondía cuando un humano le hacía una pregunta. Con la Fase 6, Lobster actúa por iniciativa propia: monitoriza el clúster Kubernetes de SaaSphere cada 5 minutos, detecta anomalías, las analiza con IA y notifica al administrador — o actúa directamente si tiene certeza suficiente.
>
> Los tres pilares que se implementan son:
> - **Scheduler** — tareas programadas (health checks, resúmenes, backups, optimización)
> - **K8s Watcher** — escucha el stream de eventos de Kubernetes en tiempo real
> - **Webhook de Alertmanager** — recibe alertas de Prometheus y las analiza con IA

> [!note] Tecnologías utilizadas
> `APScheduler 3.x` · `lightkube AsyncClient` · `FastAPI` · `Ollama (qwen3:8b / qwen3:32b)` · `Alertmanager v0.27` · `Prometheus` · `Loki` · `Telegram Bot API`

---

## Demostraciones

---

### 1. Scheduler arrancado con 6 jobs

> [!tip] Explicación para el TFG
> Al iniciar Lobster, el scheduler registra automáticamente 6 tareas sin ninguna intervención humana. Esto demuestra que el sistema opera de forma autónoma desde el primer segundo: health check cada 5 min, estado global cada 30 min, resumen horario, resumen diario a las 08:00, verificación de backups a las 02:00 y optimización a las 03:00.

> [!example] Comando para la captura
> ```bash
> journalctl -u lobster --no-pager | grep -E 'scheduler.started|k8s_watcher.started|k8s_watcher.connected'
> ```

---

### 2. Health loop ejecutándose de forma periódica

> [!tip] Explicación para el TFG
> Cada 5 minutos el agente lanza un health check rápido usando el modelo ligero `qwen3:8b`. Revisa el estado de todos los pods y deployments en los namespaces de tenant. Si todo está bien, no hace nada más. Si detecta algo anómalo, escala al análisis profundo de forma automática — sin que nadie lo ordene.

> [!example] Comando para la captura
> ```bash
> journalctl -u lobster --no-pager | grep 'health_loop_read' | tail -20
> ```

---

### 3. Detección automática de anomalías

> [!tip] Explicación para el TFG
> El sistema analiza el texto del health check buscando palabras clave: `crashloopbackoff`, `oomkill`, `error`, `failed`, `pending`, `evicted`... Si las encuentra, lanza automáticamente la fase de análisis profundo. Es el mecanismo que convierte una lectura pasiva en una acción reactiva.

> [!example] Comando para la captura
> ```bash
> journalctl -u lobster --no-pager | grep 'anomaly_detected'
> ```

---

### 4. Análisis profundo con IA (qwen3:8b + think)

> [!tip] Explicación para el TFG
> Cuando se detecta una anomalía, el agente usa `qwen3:8b` con **modo think activado**: el modelo razona internamente antes de responder, como si fuera un técnico revisando el problema paso a paso. Consulta pods en K8s, logs en Loki y métricas en Prometheus, y produce un diagnóstico estructurado.

> [!example] Comando para la captura
> ```bash
> journalctl -u lobster --no-pager | grep 'health_loop_analyze' | tail -10
> ```

---

### 5. Acción autónoma — reinicio de pod sin intervención humana

> [!danger] Explicación para el TFG
> Esta es la capacidad más avanzada y significativa del TFG. El agente no solo detecta y reporta: **actúa**. En producción real, durante esta fase, reinició un pod en el clúster de forma autónoma tras confirmar el problema — sin que nadie se lo pidiera. Esto demuestra un bucle completo de percepción → razonamiento → acción.

> [!example] Comando para la captura
> ```bash
> journalctl -u lobster --no-pager | grep 'restart_pod.called'
> ```

---

### 6. K8s Watcher conectado en tiempo real

> [!tip] Explicación para el TFG
> Además del scheduler periódico, hay un segundo mecanismo reactivo: un watcher que observa el stream de eventos de Kubernetes en tiempo real. Si aparece un evento `Warning` crítico (BackOff, OOMKilling, CrashLoop, Evicted...) lo analiza inmediatamente, sin esperar al siguiente ciclo de 5 minutos. Reconexión automática con backoff exponencial si pierde la conexión.

> [!example] Comando para la captura
> ```bash
> journalctl -u lobster --no-pager | grep -E 'k8s_watcher\.(started|connected|critical_event)'
> ```

---

### 7. Webhook de Alertmanager funcionando

> [!tip] Explicación para el TFG
> Alertmanager (el sistema de alertas de Prometheus) está configurado para enviar todas las alertas críticas a Lobster vía HTTP. El agente recibe el payload, lo analiza con IA y responde — igual que un operador humano on-call pero de forma instantánea y sin fatiga de alerta.

> [!example] Comando para la captura — lanzar alerta de prueba
> ```bash
> curl -i -X POST http://localhost:8080/webhook/alert \
>   -H 'Content-Type: application/json' \
>   -d '{
>     "status": "firing",
>     "commonLabels": {"alertname": "TestAlert", "severity": "warning"},
>     "commonAnnotations": {"summary": "Prueba de integración TFG"},
>     "alerts": [{
>       "status": "firing",
>       "labels": {"alertname": "TestAlert"},
>       "annotations": {"summary": "Prueba TFG"},
>       "startsAt": "2026-05-14T00:00:00Z"
>     }]
>   }'
> ```

> [!example] Comando para ver que llegó al sistema
> ```bash
> journalctl -u lobster --no-pager | grep 'webhook.alert_received' | tail -5
> ```

---

### 8. Métricas del propio agente en Prometheus

> [!tip] Explicación para el TFG
> Lobster expone sus propias métricas en formato Prometheus: cuántos ciclos ha ejecutado cada job, cuándo fue el último, cuántos webhooks ha recibido y con qué outcome. Esto permite monitorizar al monitor — el sistema es observable por sí mismo.

> [!example] Comando para la captura
> ```bash
> curl -s http://localhost:8080/metrics | grep -E 'lobster_(scheduler_runs|last_cycle|webhook)'
> ```

---

### 9. Enrutamiento de modelos según complejidad de la tarea

> [!tip] Explicación para el TFG
> El sistema no usa siempre el mismo modelo. Implementa una política de enrutamiento basada en la complejidad esperada de la tarea: `qwen3:8b` sin think para lecturas rápidas, `qwen3:8b` con think para análisis reactivos, y `qwen3:32b` para el resumen diario completo. Esto demuestra una arquitectura consciente del coste computacional.

> [!example] Comando para la captura
> ```bash
> cat /opt/lobster/lobster_agent/agent/routing.py
> ```

---

### 10. Resumen diario completo (qwen3:32b a las 08:00)

> [!tip] Explicación para el TFG
> Cada día a las 08:00 el agente genera un resumen operativo completo: estado global de tenants, recursos consumidos, certificados próximos a vencer, decisiones tomadas en las últimas 24 horas. Este job usa `qwen3:32b` porque requiere síntesis y razonamiento más profundo. El resultado llega por Telegram en formato Markdown.

> [!example] Comando para ver el próximo disparo programado
> ```bash
> journalctl -u lobster --no-pager | grep 'daily_summary' | tail -5
> ```

---

### 11. Notificación en Telegram al administrador

> [!tip] Explicación para el TFG
> Cada análisis relevante llega automáticamente al administrador por Telegram. El sistema actúa como un operador de guardia 24/7 que avisa solo cuando es necesario y con contexto suficiente para actuar. No hay polling manual ni dashboards que revisar.

> [!example] Captura
> *(Captura manual del mensaje recibido en el móvil — mostrar el análisis de `health_loop_analyze` con los hallazgos sobre `helm-install-traefik` y `coredns`)*

---

## Diagrama del flujo autónomo

```
K8s Cluster
    │
    ├─► K8s Watcher ──────────────────────────────────────┐
    │   (eventos en tiempo real)                           │
    │                                                      ▼
    └─► Scheduler (cada 5 min) ──► health_loop_read    ANALYZE
                                        │               (8b+think)
                                   ¿anomalía?               │
                                        │ sí                 ▼
                                        └──────────► Telegram Admin

Alertmanager ──► POST /webhook/alert ──► ALERT_REACTIVE ──► Telegram
                                         (8b+think)
```

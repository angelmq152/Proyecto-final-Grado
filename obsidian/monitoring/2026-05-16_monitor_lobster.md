---
tags: [lobster, monitoring, tfg]
created: 2026-05-16T19:07:33+02:00
closed: 2026-05-16T23:15:55+02:00
status: cerrado
---

# Monitoreo Lobster — 2026-05-16

> [!info] Sesión de observación
> Monitoreo en vivo del agente Lobster iniciado a las **19:07:33 CEST**. Modo *solo lectura* — no se ejecuta ninguna mutación. El informe se actualiza con cada ciclo de revisión hasta que el operador pida finalizarlo.

---

## 1. Estado del sistema (snapshot inicial)

| Componente | Valor |
|---|---|
| Servicio systemd | `lobster.service` — **active (running)** |
| Arranque actual | 2026-05-16 19:00:38 CEST (PID 1035641) |
| Versión | 0.1.0 |
| Uptime al iniciar monitoreo | ~6 min 55 s |
| Memoria | 177.9 MB (peak 179.3 MB) |
| Endpoint `/health` | `{"status":"ok","uptime_seconds":399.89}` |
| Modo agente (`agent_state.mode`) | **`normal`** — *"preparar demo aprobaciones"*, fijado 2026-05-13 22:03 |
| Base de datos | `/var/lib/lobster/state.db` (864 KB + WAL 152 KB) |

### Jobs programados (APScheduler)

| Job | Próxima ejecución |
|---|---|
| `health_loop` | 2026-05-16 19:05:39 |
| `global_state` | 2026-05-16 19:30:39 |
| `hourly_summary` | 2026-05-16 20:00:00 |
| `daily_summary` | 2026-05-17 00:15:00 |
| `backup` | 2026-05-17 02:00:00 |
| `optimization` | 2026-05-17 03:00:00 |

> [!note] Endpoint `/admin/queue`
> Devuelve 404 → la cola de Fase 9 (`worktree-fase-9-job-queue`) **no está fusionada en `main`** todavía. Coherente con el "Pendiente de despliegue" en [[TFG_Fase9_Lobster]].

---

## 2. Totales en base de datos

| Tabla | Filas |
|---|---|
| `decisions` | 414 |
| `actions` | 18 |
| `approvals` | 14 |
| `events` | 0 *(no se está poblando — ver §6)* |
| `tool_requests` | 6 |
| `metrics_snapshots` | 0 |

---

## 3. Decisiones del agente

### 3.1 Reparto por `case_use` (últimas 24 h)

| Case use | Nº | Latencia media (s) |
|---|---:|---:|
| `health_loop_read` | 114 | 48.7 |
| `alert_reactive` | 26 | 161.3 |
| `global_state` | 18 | 81.6 |
| `chat` | 13 | 58.1 |
| `summary` | 12 | 37.1 |
| `health_loop_analyze` | 3 | 109.7 |
| `daily_summary` | 1 | 541.5 |
| `node_pressure` | 1 | 481.7 |

> [!observation] Comentario
> El `health_loop_read` domina (≈80 % del volumen) porque corre cada 5 min con `qwen3:8b`. El único `daily_summary` ronda los **9 min**, encajando con el rango esperado para `qwen3:32b` (ver [[project_lobster_ollama_timeout]]).

### 3.2 Últimas 10 decisiones (más reciente arriba)

| Timestamp | Case use | Modelo | Think | Latencia | Cabecera |
|---|---|---|---|---:|---|
| 17:05:39 | health_loop_read | qwen3:8b | No | 34 s | [OK] Pods Running/Succeeded |
| 17:05:21 | chat | qwen3:8b | No | 43 s | Tenant **saasphere** listo (saasphere.local) |
| 17:01:49 | alert_reactive | qwen3:8b | No | 90 s | Alerta `LobsterRestart` — falsa positiva |
| 17:00:00 | summary | qwen3:8b | No | 28 s | Resumen horario |
| 16:57:49 | alert_reactive | qwen3:8b | No | 18 s | Restart detectado (uptime 1m 45s) |
| 16:56:22 | health_loop_read | qwen3:8b | No | 60 s | [OK] sin anomalías |
| 16:55:56 | chat | qwen3:8b | No | 94 s | Necesita confirmar `tenant_type` |
| 16:53:19 | chat | qwen3:8b | No | 198 s | El sistema rechaza `tenant_type` |
| 16:52:49 | alert_reactive | qwen3:8b | No | 140 s | No encontró recurso "Lobster" |
| 16:52:40 | chat | qwen3:8b | No | 6 s | Usuario pide tenant "saasphere" sin tipo |

> [!warning] Patrón observado
> A las 16:52-16:55 hay un bucle de chat por `tenant_type` rechazado: el modelo intenta varios valores y el sistema los aborta. Se documenta como **tool_request pendiente**: `Validate tenant_type options` (creado 16:57:14, todavía `pending`).

---

## 4. Mutaciones (`actions` ledger)

### 4.1 Histograma global

| Estado | Nº | | Severidad | Nº |
|---|---:|---|---|---:|
| completed | 10 | | autonomous | 5 |
| failed | 3 | | critical | 9 |
| aborted_policy | 3 | | forbidden | 3 |
| approved (sin completar) | 1 | | normal | 1 |
| rejected | 1 | | | |

### 4.2 Últimas mutaciones relevantes

| Timestamp | Tipo | Namespace | Severidad | Estado | Nota |
|---|---|---|---|---|---|
| 17:05:26 | deploy_tenant | saasphere | critical | OK completed | Tenant re-creado tras delete previo |
| 16:42:46 | delete_tenant | saasphere | critical | OK completed | |
| 16:06:08 | deploy_tenant | saasphere | critical | OK completed | |
| 15:25:59 | deploy_tenant | saasphere | critical | WARN approved | *Aprobada pero no marcada como completed* |
| 2026-05-14 23:13 | update_configmap | default | forbidden | BLOCK aborted_policy | Bloqueado por política (namespace fuera de tenant) |
| 2026-05-14 00:20 | deploy_tenant | prueba-tfg | critical | FAIL failed | RBAC: `system:serviceaccount:saasphere-system:lobster-reader` no puede crear deployments |
| 2026-05-13 23:35 | restart_pod | demo-tfg | forbidden | BLOCK aborted_policy | |
| 2026-05-12 21:16 | deploy_tenant | demo-tfg | critical | FAIL rejected | Approval rechazada o expirada |

> [!warning] Inconsistencia detectada
> La action `a45c24e5…deploy_tenant` (15:25:59) tiene status `approved` pero **no** pasó a `completed`. Vale la pena verificar si quedó colgada o si el siguiente deploy a las 16:06 la sustituyó implícitamente.

---

## 5. Aprobaciones (Telegram)

| Timestamp | Tipo | Severidad | Estado | Decisión en |
|---|---|---|---|---:|
| 17:05:26 | deploy_tenant | critical | approved | 24 s |
| 16:42:46 | delete_tenant | critical | approved | 1 min 44 s |
| 16:06:08 | deploy_tenant | critical | approved | 58 s |
| 15:25:59 | deploy_tenant | critical | approved | 1 min 8 s |
| 2026-05-14 00:22 | deploy_tenant | critical | approved | 2 s |
| 2026-05-12 21:16 | deploy_tenant | critical | expired | (sin decisión en plazo) |
| 2026-05-11 21:58 | restart_pod | normal | expired | |

> [!note] Tiempo medio de respuesta humana
> Las 4 aprobaciones de hoy se decidieron en una media de **48 s**. No hay aprobaciones pendientes en este snapshot.

---

## 6. Eventos / anomalías

- **`events` table = 0 filas.** No se está poblando — fuente esperada: `EventRepository` (o aún sin wiring). Los eventos relevantes están emergiendo en otros lugares:
  - **Alertmanager** vía `/webhook/alert` → 2 alertas recibidas (status 202) → ambas tipo `LobsterRestart`.
  - **Logs structlog** vía journald → activos.
- **Tool requests pendientes (6):** `deploy_tenant`, `record_snapshot`, `check_backup_status`, `tenant_type_validator`, `deploy_static_site`, `deploy_wordpress_tenant`. Todas `pending`.
- **Errores recientes en mutaciones:**
  - 3 × `aborted_policy` (política bloqueó la acción) → comportamiento correcto.
  - 3 × `failed` con RBAC (`lobster-reader` no puede crear Deployments) → revisar `ClusterRoleBinding`.

---

## 7. Métricas Prometheus (selección)

```
lobster_uptime_seconds                              ~400
lobster_http_requests_total{endpoint="/health"}     1
lobster_http_requests_total{endpoint="/webhook/alert",status="202"}  2
lobster_http_requests_total{endpoint="/metrics"}    26
lobster_decisions_total{case_use="alert_reactive"}  1  (post-restart)
lobster_decisions_total{case_use="chat"}            1
lobster_decisions_total{case_use="health_loop_read"} 1
lobster_llm_latency_seconds_sum{alert_reactive}     90.57 s
```

---

## 8. Ciclos de revisión

> [!tip] Convención
> Cada ciclo añade una entrada en esta sección con: timestamp, deltas observados (nuevas decisions / actions / approvals / errores) y comentario.

### Ciclo 0 — 19:07:33 — *snapshot inicial*

- Línea base capturada (todo lo anterior).
- Próximo health_loop esperado: 19:05:39 (ya pasó) → siguiente en ~5 min.
- Siguiente hito relevante: `hourly_summary` a las 20:00:00.

### Ciclo 1 — 19:43:37 — *health loop estable, una alerta resuelta*

- Servicio: **active** · uptime: 2578 s (~43 min) · modo: **normal**
- Decisions nuevas: **9**
  - 19:06:49 alert_reactive 80.7 s — `LobsterRestart` resuelta (pod `saasphere-58ddf785b...` Running)
  - 19:10:39 health_loop_read 104.8 s — [OK] pods Running
  - 19:15:39 health_loop_read 56.2 s — [OK]
  - 19:20:39 health_loop_read 38.7 s — [OK]
  - 19:25:39 health_loop_read 33.8 s — [OK]
  - 19:30:39 health_loop_read 62.5 s — [OK]
  - 19:30:39 **global_state** qwen3:8b *+think* 110.5 s — snapshot global generado
  - 19:35:39 health_loop_read 37.4 s — [OK]
  - 19:40:39 health_loop_read 47.2 s — [OK]
- Actions nuevas: **0**
- Approvals nuevas: **0** · pendientes: **0**
- Errores en logs: **0**
- Tool requests pendientes: 6 (sin cambios)
- Comentario: ritmo estable de `health_loop_read` cada 5 min, latencias entre 33-104 s. El `alert_reactive` posterior al snapshot inicial confirmó que el `LobsterRestart` era falso positivo del propio reinicio del agente.

### Ciclo 2 — 19:48:17 — *salud estable*

- Servicio: **active** · uptime: 2859 s (~47 min) · modo: **normal**
- Decisions nuevas: **1**
  - 19:45:39 health_loop_read 15.6 s — [OK] pods Running, ≤5 reinicios
- Actions nuevas: **0**
- Approvals nuevas: **0** · pendientes: **0**
- Errores en logs: **0**
- Comentario: latencia del `health_loop_read` se reduce a 15.6 s (la más baja del día); cluster sigue limpio.

### Ciclo final — 23:15:55 — *cierre del monitoreo (cobertura 20:00 → 23:15)*

- Servicio: **active** · uptime: 15 317 s (~4 h 15 min) · modo: **normal**
- Decisions nuevas (desde 20:00 CEST): **46**
  - 36 × `health_loop_read` (avg 35.9 s · min 15.2 s · max 92.7 s)
  - 6 × `global_state` con think=1 (avg 63.0 s)
  - 4 × `summary` horario (avg 18.1 s)
- Actions nuevas: **0**
- Approvals nuevas: **0** · pendientes: **0**
- Errores en logs: **3 timeouts del scheduler**
  - 22:10:39 — `health_loop_read` timeout (300 s) + `global_state` timeout (600 s) → ambos coincidentes; el siguiente health_loop fue **skipped** por APScheduler: *"maximum number of running instances reached (1)"*. Reanudación normal a las 22:15:39.
  - 23:15:39 — otro `health_loop_read` timeout (300 s), justo en el momento del cierre del monitoreo.

> [!warning] Anomalía relevante observada
> El gap de 5 minutos entre 22:10 y 22:15 confirma exactamente el problema que motivó la **Fase 9** ([[TFG_Fase9_Lobster]]): sin cola FIFO, un job lento del LLM bloquea al siguiente y APScheduler descarta el solapado. Misma firma en 23:15. La cola sigue **sin desplegar** (`/admin/queue` devuelve 404), así que el riesgo persiste.

<!-- FIN DE CICLOS DE REVISIÓN -->

---

## 9. Conclusiones

### 9.1 Duración y volumen

- **Ventana de observación:** 2026-05-16 19:07:33 → 23:15:55 CEST · **4 h 8 min**.
- **Decisions observadas:** 56 nuevas (de 414 a 472 en BD).
- **Actions nuevas:** 0 — no hubo ninguna mutación durante el monitoreo.
- **Approvals nuevas:** 0 — y 0 pendientes al cierre.
- **Servicio:** se mantuvo `active` durante toda la ventana, sin reinicios, sin caídas de `/health`.

### 9.2 Reparto por `case_use` durante el monitoreo

| Case use | Nº | Latencia media | Comentario |
|---|---:|---:|---|
| `health_loop_read` | 45 | ~35 s | Cumple frecuencia objetivo (cada 5 min) |
| `global_state` | 7 | ~70 s | think=1 activado, ritmo correcto (cada 30 min) |
| `summary` | 5 | ~22 s | Resúmenes horarios |
| `alert_reactive` | 1 | 81 s | `LobsterRestart` resuelta como falso positivo |

### 9.3 Anomalías detectadas

> [!warning] 1. Timeouts del scheduler (3 incidentes)
> A las **22:10:39 CEST** un `health_loop_read` y un `global_state` superaron sus timeouts (300 s / 600 s) y APScheduler descartó la siguiente fire por contención (`maximum number of running instances reached (1)`). El mismo patrón se repitió a las **23:15:39 CEST**. Esto es exactamente el síntoma que motiva la **Fase 9** (cola FIFO serializada en Ollama). El branch `worktree-fase-9-job-queue` está listo pero `/admin/queue` sigue devolviendo 404 → **no se ha mergeado a main**.

> [!warning] 2. Action `approved` sin `completed` (15:25:59)
> La action `a45c24e5…deploy_tenant` quedó en estado `approved` y nunca pasó a `completed`. El deploy posterior a las 16:06 sí completó. Posiblemente colgado por la misma contención de Ollama o por un error silenciado antes del Ciclo 0.

> [!warning] 3. Tabla `events` vacía
> Los eventos `EventRepository` no se persisten (0 filas), pese a que sí se reciben alertas por `/webhook/alert`. Wire pendiente en `lobster_agent/persistence/repositories.py` o en el handler del webhook.

> [!warning] 4. Tool requests sin atender
> 6 `tool_requests` en estado `pending` desde 2026-05-12 (la más reciente del 16-05 a las 16:57). El agente está solicitando capacidades (`tenant_type_validator`, `record_snapshot`, `check_backup_status`, etc.) pero nadie las recoge.

### 9.4 Cosas que funcionan bien

- **Aprobaciones humanas vía Telegram**: las 4 aprobaciones del día se decidieron en 24–104 s (media 48 s). Flujo cómodo.
- **Política de namespace**: 3 mutaciones bloqueadas correctamente con `aborted_policy` (intento de tocar `default/registry-creds` y `restart_pod` en pods no etiquetados como tenant). El guardrail funciona.
- **Latencia del `health_loop_read`**: la mayoría termina en <30 s, encajando con la definición de la Fase 9 (umbral para considerar un job "directo").

### 9.5 Recomendaciones

1. **Mergear `worktree-fase-9-job-queue` a `main` y reiniciar el servicio.** Eliminaría los timeouts por contención. Plan ya redactado en [[TFG_Fase9_Lobster]] §"Checklist de despliegue".
2. **Revisar el RBAC del `ServiceAccount` `lobster-reader`** para conceder `create deployments` en namespaces de tenant. Hay 3 actions históricas `failed` por esto.
3. **Auditar la action `a45c24e5…` colgada en `approved`** y añadir un job de barrido que reconcilie acciones aprobadas sin completar tras N minutos.
4. **Implementar la población de `events`** o eliminar la tabla si no se usa.
5. **Triar los 6 `tool_requests` pendientes**: cerrar los obsoletos y promover los útiles a tools reales (`tenant_type_validator` es el más urgente — ya causó un bucle de chat de 4 minutos el 16-05 16:52-16:55).

### 9.6 Ficheros y enlaces relevantes

- Informe: `obsidian/monitoring/2026-05-16_monitor_lobster.md` (este fichero)
- Cursor de monitoreo: `/home/angel/.claude/jobs/fd710975/monitor_state.json`
- DB: `/var/lib/lobster/state.db`
- Logs: `journalctl -u lobster`
- Notas relacionadas: [[TFG_Fase9_Lobster]] · [[TFG_Fase8_Lobster]] · [[project_lobster_ollama_timeout]] · [[feedback_validacion_natural]]

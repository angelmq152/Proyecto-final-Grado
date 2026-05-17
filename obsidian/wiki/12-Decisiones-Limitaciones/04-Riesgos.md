---
title: Riesgos
tags: [decisiones, riesgos, seguridad, tfg]
---

# ⚠️ Riesgos conocidos

> [!abstract] Mapa de riesgos
> Lo que puede salir mal y cómo de probable es. Sin endulzar.

## 🔴 Alto impacto

### R1 — LLM ejecuta una mutación errónea por nombre inventado

> [!danger] Probabilidad: media · Impacto: alto
> El LLM, bajo presión, invoca `restart_pod(namespace="default", pod_name="nginx-inexistente")`.

**Hoy mitigado por**:
- Prompt explícito ("verifica con list_pods primero").
- `K8sClientError` si el recurso no existe (la mutación falla, no pasa nada).
- Aprobación humana para mutaciones NORMAL/CRITICAL.

**Residual**: el `restart_pod` autónomo en CrashLoopBackOff podría ejecutarse contra el pod equivocado **si** la condición CrashLoop se cumple en otro pod. En la práctica, hasta hoy no ha ocurrido.

### R2 — Manifest aplicado escapa a policy

> [!danger] Probabilidad: baja · Impacto: alto
> El LLM construye un manifest que pasa la validación pero hace algo inesperado (p.ej. usa un `image` malicioso).

**Hoy mitigado por**:
- Validación de kinds permitidos.
- Bloqueo de privileged/hostPath/etc.
- Limits de recursos obligatorios.
- RBAC K8s solo permite ciertos verbs.

**Residual**: imagen Docker con código dañino. No hay scanning de imágenes.

### R3 — Borrado accidental por delete_tenant

> [!danger] Probabilidad: baja · Impacto: muy alto
> Operador (o LLM) ejecuta `delete_tenant("tenant-acme", confirm="tenant-acme")`. Acme se va.

**Hoy mitigado por**:
- Confirmación textual exacta.
- Severidad CRITICAL → mensaje Telegram con timeout 1h y recordatorios.

**Residual**: sin backup automático, el namespace + PVCs se pierden. Mitigación operativa: tener backups externos.

## 🟠 Medio impacto

### R4 — Ollama caído sin notify

> [!warning] Probabilidad: media · Impacto: medio
> Ollama se reinicia o crashea. Hasta que vuelve, `lobster_decisions_total{outcome="failed"}` sube.

**Hoy mitigado por**:
- Alerta `LobsterDecisionesFallidas` dispara > 30% failed.
- Métrica `lobster_errors_total` registra.

**Residual**: si Ollama tarda mucho en reiniciar (modelo no se carga), tampoco hay alerta directa. Roadmap: alerta específica de Ollama desde Prom.

### R5 — Loki cola llena

> [!warning] Probabilidad: baja · Impacto: medio
> Loki cae 1 hora. La cola `_queue: asyncio.Queue(maxsize=1000)` se llena. Nuevos logs se silencian.

**Hoy mitigado por**:
- Métrica `lobster_loki_queue_size`.
- stdout sigue funcionando → journald captura todo.

**Residual**: ningún panel se queja por sí solo de "logs no llegando a Loki" más allá de la métrica de cola.

### R6 — Aprobación expirada durante mutación

> [!warning] Probabilidad: baja · Impacto: medio
> Operador tarda > 10 min en aprobar una NORMAL → expira → mutación se aborta. Pero el problema que la motivó (alerta) sigue.

**Hoy mitigado por**:
- Mensaje EXPIRED al operador.
- La alerta sigue activa en Alertmanager → re-dispara webhook.

## 🟡 Bajo impacto

### R7 — Inflación de tablas SQLite

> [!info] Probabilidad: alta · Impacto: bajo
> Tras años, `decisions` tiene 1M filas. `actions` 50k. Queries lentas.

**Hoy mitigado por**:
- Índices en `timestamp`, `case_use`, `created_at`, etc.

**Residual**: `VACUUM` manual ocasional. Roadmap: TTL configurable.

### R8 — Token Telegram filtrado

> [!info] Probabilidad: baja · Impacto: bajo (para SaaSphere)
> El token está en `/etc/lobster/.env`. Si se filtra, un atacante puede mandar mensajes al bot pero no recibe respuesta (sin allowed_user_ids).

**Hoy mitigado por**:
- `is_allowed()` en cada handler.
- Permisos 600 en `.env`.

### R9 — SQLite corruption por kill -9

> [!info] Probabilidad: baja · Impacto: bajo
> Si LeIA pierde energía con escrituras en vuelo, el WAL puede quedar inconsistente.

**Hoy mitigado por**:
- WAL + `synchronous=NORMAL` ya es resiliente.
- En el peor caso, las últimas transacciones se rollback.

## 🛡️ Riesgos cubiertos por arquitectura

### R10 — LLM intenta mutar kube-system

✅ **Doble bloqueo**: `policy.py` rechaza + RBAC K8s rechaza. Imposible.

### R11 — LLM intenta crear ClusterRoleBinding

✅ `apply_manifest` rechaza kinds prohibidos antes de tocar K8s.

### R12 — LLM intenta `kubectl exec`

✅ **No hay tool para esto**. Pydantic-AI solo expone las funciones registradas. El LLM no puede inventar herramientas.

### R13 — Usuario no autorizado en Telegram

✅ `is_allowed()` rechaza con log warning.

## 🧪 Riesgos no contemplados

> [!warning] Honestidad: lo que NO se ha probado
> - **Inyección de prompt** en `prompt_summary` (un tenant con descripción maliciosa). Hoy ningún tenant tiene esto.
> - **Tormenta de webhooks** > 1000/min. Alertmanager no debería emitir tantos, pero no se probó.
> - **Reentrada del watcher** durante reconexión rápida. Lightkube reconnect tiene su propio backoff.

→ Sigue en [[05-Futuro-roadmap]].

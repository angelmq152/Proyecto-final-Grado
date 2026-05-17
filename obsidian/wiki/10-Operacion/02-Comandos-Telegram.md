---
title: Operación — Comandos Telegram
tags: [operacion, telegram, comandos]
---

# 📱 Telegram · Comandos operativos

> [!abstract] El control desde el móvil
> Toda la operación que el autor hace en movilidad. Solo los `allowed_user_ids` pueden ejecutar comandos. Mensajes no autorizados se ignoran (con log warning).

## 🚏 Tabla rápida

| Comando | Acción |
|---|---|
| `/start` | Saludo y ayuda básica |
| `/help` | Lista completa de comandos |
| `/status` | Modo, pendientes y última decisión |
| `/pending` | Aprobaciones pendientes |
| `/show <id>` | Detalle de una aprobación (id completo o prefijo 8 chars) |
| `/pause [razón]` | Pasa a modo `dry_run` |
| `/resume` | Vuelve a modo `normal` |
| `/kill [razón]` | Pasa a modo `paused` (LLM detenido) |
| `/think <pregunta>` | Razonamiento profundo (qwen3:32b + think) |
| `/forget` | Borra historial del chat |
| `/toolrequests` | Lista solicitudes de herramientas pendientes |
| Texto libre | Enrutado como `CaseUse.CHAT` |

## 🎯 Texto libre vs comandos

> [!tip] Cuándo usar /think vs texto libre
> - **Texto libre** → respuesta rápida con qwen3:8b sin think (~10-30 s).
> - **/think** → análisis profundo con qwen3:32b + think (~3-8 min).

## 🚦 `/status`

> [!example] Output
> ```
> 🟢 Modo: normal
> 📊 Pendientes: 0
> 🔍 Última decisión: approved
> ```
> Emoji por modo: 🟢 normal, 🟡 dry_run, 🔴 paused.

## 📋 `/pending` y `/show`

> [!example] `/pending`
> ```
> ⚠️ `a5f23c91` restart_deployment _normal_ age=42s
> 🚨 `b8e91234` deploy_tenant _critical_ age=180s
> ```
>
> `/show a5f23c91` muestra el detalle completo igual que el mensaje original.

## ⏸️ Cambio de modo

| Comando | Modo resultante | Notify a admin |
|---|---|---|
| `/pause razón` | `dry_run` | 🟡 |
| `/resume` | `normal` | 🟢 |
| `/kill razón` | `paused` | 🔴 |

## 🧠 `/think`

> [!example] Flujo
> 1. Operador: `/think ¿por qué el daily summary de ayer dijo X?`
> 2. Bot: *"🧠 Pensando con razonamiento profundo…"*
> 3. (cada 60 s actualiza: *"🧠 Pensando… (3 min)"*)
> 4. Bot: respuesta en MarkdownV2 con el razonamiento.
> 5. Bot añade el turno a `conversation_turns`.

## 🗑️ `/forget`

Limpia tanto RAM como SQLite para ese chat. Útil cuando empezar fresh tras cambiar de tema completamente.

## 🔧 `/toolrequests`

> [!example] Lista las 10 últimas pendientes
> ```
> 🔧 `42` get_pod_history — permite leer eventos de un pod ya borrado
> 🔧 `43` query_metrics_dashboard — devuelve gráficos como imágenes
> ```

## ✅❌ Botones inline en aprobaciones

> [!info] No son comandos pero forman parte de la operación
> Cuando llega una aprobación, los botones son:
> - **Aprobar** → ejecuta la mutación.
> - **Rechazar** → aborta. Action queda `REJECTED`.
> - **Pausar todo** → cambia modo a `dry_run` (no rechaza la actual).

→ Detalle visual en [[../04-Telegram/03-Aprobaciones-inline]].

## 🛡️ Seguridad

> [!danger] Solo los user IDs whitelisted
> `is_allowed(event, settings)` filtra. Los IDs se configuran en `[telegram] allowed_user_ids = [...]`. Si un usuario no autorizado escribe, se loguea `lobster.telegram.unauthorized` con su user_id y username.

> [!tip] Obtener tu user ID
> Habla con `@userinfobot` en Telegram. Te devuelve tu ID. Añádelo al config y reinicia Lobster.

---
title: Telegram — Handlers y comandos
tags: [telegram, handlers, comandos, aiogram]
---

# 📲 Telegram · Handlers y comandos

> [!abstract] Cómo se atan los comandos a su lógica
> Archivo: `lobster_agent/telegram/handlers.py`. Usa `aiogram.Router` para registrar cada `Command(...)` y un callback handler para botones inline. Todo handler **primero** llama `is_allowed(event, settings)` y aborta si el usuario no está en `allowed_user_ids`.

## 🗺️ Router

```python
def build_router() -> Router:
    router = Router()
    router.message.register(handle_start,       Command("start"))
    router.message.register(handle_help,        Command("help"))
    router.message.register(handle_status,      Command("status"))
    router.message.register(handle_pending,     Command("pending"))
    router.message.register(handle_show,        Command("show"))
    router.message.register(handle_pause,       Command("pause"))
    router.message.register(handle_resume,      Command("resume"))
    router.message.register(handle_kill,        Command("kill"))
    router.message.register(handle_think,       Command("think"))
    router.message.register(handle_forget,      Command("forget"))
    router.message.register(handle_toolrequests,Command("toolrequests"))
    router.callback_query.register(handle_approve_callback, lambda c: c.data.startswith("approve:"))
    router.callback_query.register(handle_reject_callback,  lambda c: c.data.startswith("reject:"))
    router.callback_query.register(handle_pause_all_callback, lambda c: c.data == "pause_all")
    router.message.register(handle_free_text,   F.text)        # último: cualquier texto
    return router
```

## 🧾 Comandos en detalle

### `/start` y `/help`

> [!example] Output de `/help`
> ```
> 📖 *Comandos disponibles:*
>
> /status — estado del agente
> /pending — aprobaciones pendientes
> /show <id> — detalle de una aprobación
> /pause [razón] — modo dry_run
> /resume — volver a modo normal
> /kill [razón] — pausar completamente
> /think <pregunta> — razonamiento profundo
> /forget — borrar historial del chat
> /toolrequests — solicitudes de herramientas
> ```

### `/status`

> [!example] Salida
> ```
> 🟢 Modo: normal
> 📊 Pendientes: 0
> 🔍 Última decisión: approved
> ```
> Lee `AgentState`, cuenta pending approvals, devuelve el status del último approval listado.

### `/pending`

Devuelve una línea por aprobación pending: `{severity_emoji} {short_id} {action_type} {severity} age=Ns`.

### `/show <id>`

Acepta el id completo o un prefijo de 8 caracteres (`approval.id.startswith(id_arg)`). Imprime el detalle MarkdownV2 igual que el mensaje original.

### `/pause`, `/resume`, `/kill`

Cambian `agent_state.mode`:
- `/pause` → `DRY_RUN` (razón opcional como argumento).
- `/resume` → `NORMAL`.
- `/kill` → `PAUSED`.

Cada uno envía además un alert a admin: `🟡 Modo cambiado a dry_run`.

### `/think <pregunta>`

> [!info] Razonamiento profundo
> 1. Crea placeholder *"🧠 Pensando con razonamiento profundo…"*.
> 2. Arranca tick task que actualiza el placeholder cada minuto con *"🧠 Pensando… (X min)"*.
> 3. Ejecuta `agent.run(CaseUse.THINK, text, message_history=memory)`.
> 4. Reemplaza placeholder con la respuesta MarkdownV2.
> 5. Persiste user+assistant turns en memory.

### `/forget`

`memory.clear(chat_id)` → borra el chat tanto en RAM como en SQLite (`conversation_turns`).

### `/toolrequests`

Muestra las 10 últimas `ToolRequest` con `status="pending"`.

## 💬 Texto libre

```python
async def handle_free_text(message, settings, agent, memory, **_):
    if not is_allowed(message, settings): return
    text = message.text
    if text.startswith("/"): return        # ignora comandos no registrados
    ...
    result = await agent.run(CaseUse.CHAT, text, message_history=memory.get_history(chat_id))
    ...
```

> [!tip] Por qué se enruta como CHAT
> `CaseUse.CHAT` usa `qwen3:8b` sin think → respuestas rápidas. Si el operador quiere razonamiento profundo usa `/think`.

## 🛡️ Guard de seguridad

```python
def is_allowed(event, settings) -> bool:
    user_id = getattr(getattr(event, "from_user", None), "id", None)
    if user_id in settings.telegram.allowed_user_ids:
        return True
    log.warning("lobster.telegram.unauthorized", user_id=user_id, ...)
    return False
```

Todos los handlers (mensajes y callbacks) lo aplican. Sin esto, cualquier persona que encuentre el bot podría pedir cambios.

## 🎨 Renderizado

Todo mensaje usa `ParseMode.MARKDOWN_V2`. La conversión Markdown→MDV2 está en `formatting.py`:
- `esc()` escapa los 18 caracteres especiales.
- `bold()`, `italic()`, `code()`, `pre()` envuelven texto ya escapado.
- `md_to_mdv2()` convierte respuestas LLM markdown → MDV2.

→ [[05-Formatting-MarkdownV2]] para el detalle.

---
title: Telegram — Notifier
tags: [telegram, notifier, helper, aprobaciones]
---

# 📨 Telegram · `TelegramNotifier`

> [!abstract] El "buzón" desde el código
> Archivo: `lobster_agent/telegram/notifier.py`. Mientras los handlers reciben mensajes del operador, el `TelegramNotifier` es el **camino contrario**: cualquier parte de Lobster (scheduler, watcher, approvals, meta tools) lo llama para emitir mensajes al admin.

## 🧬 API

```python
class TelegramNotifier:
    def __init__(self, settings, bot=None): ...

    @property
    def enabled(self) -> bool: ...

    async def post_approval_request(self, approval) -> tuple[int, int]: ...
    async def update_approval_message(self, approval) -> None: ...
    async def send_reminder(self, approval) -> None: ...
    async def send_alert(self, text) -> None: ...
    async def send_to_admin(self, text) -> None: ...
```

## 🎬 Métodos

### `post_approval_request(approval)`

Envía el mensaje con teclado inline (Aprobar/Rechazar/Pausar todo) al primer `allowed_user_ids[0]`. Devuelve `(chat_id, message_id)` para que `ApprovalManager` los persista en la fila `Approval`.

### `update_approval_message(approval)`

Edita el mensaje original (`edit_message_text` con `reply_markup=None`) para mostrar el estado resuelto. Usa los IDs guardados.

### `send_reminder(approval)`

Envía un mensaje nuevo (no edición) recordando que la aprobación sigue pendiente:
```
⏰ Recordatorio: aprobación `a5f23c91` sigue pendiente.
```

### `send_alert(text)`

Manda `text` a TODOS los `allowed_user_ids` (no solo al primero). Útil para "cambio de modo" o "Lobster arrancando".

### `send_to_admin(text)`

Manda solo al primer admin. Es el camino usado por:
- `scheduler` para emitir el header `🩺 Lobster [health_loop_read]`.
- `watcher` para `👁️ Lobster [watcher/CrashLoopBackOff]`.
- `request_new_tool` para `🔧 Nueva solicitud de herramienta`.

## 🛡️ Modo deshabilitado

```python
@property
def enabled(self) -> bool:
    return self.settings.telegram.enabled and self.bot is not None
```

Si está disabled, todos los métodos hacen no-op + log:
```
INFO lobster.telegram.alert_stubbed
INFO lobster.telegram.approval_stubbed approval_id=...
```

Es esencial para tests y para correr Lobster sin bot (smoke tests CI).

## 🤝 `FakeTelegramNotifier` para tests

```python
class FakeTelegramNotifier(TelegramNotifier):
    def __init__(self, settings):
        super().__init__(settings, None)
        self.calls: list[tuple[str, Any]] = []

    async def post_approval_request(self, approval):
        self.calls.append(("post_approval_request", approval.id))
        return (0, 0)
    ...
```

Las suites usan este fake para verificar que un código emitió la llamada correcta sin tocar la red.

## 🎨 Mensajes con formato

Todos los métodos usan `parse_mode=ParseMode.MARKDOWN_V2`. El payload se construye con `format_approval_request` / `format_approval_resolved` que están en `messages.py`. El cuerpo del payload se escapa con `pre()` (JSON pre-formateado) para evitar problemas con caracteres especiales en el dict.

→ Ver [[05-Formatting-MarkdownV2]].

## 🔌 Cómo se inyecta

En `main.py`:

```python
notifier = TelegramNotifier(settings)
# bot_runner.start() le asigna después: notifier.bot = self.bot

approval_manager = ApprovalManager(..., notifier, ...)
scheduler = SchedulerRunner(..., notifier, ...)
k8s_watcher = K8sWatcher(..., notifier)
```

> [!tip] Sesión compartida
> El bot se crea **una vez** en el TelegramBotRunner y se comparte con el notifier para reusar la sesión HTTP. Esto evita abrir N conexiones SSL hacia api.telegram.org.

→ Cierra la sección. Sigue [[../05-Persistencia/00-MOC-Persistencia|Persistencia]].

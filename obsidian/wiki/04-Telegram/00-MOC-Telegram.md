---
title: 04 · Telegram — MOC
tags: [moc, telegram, aiogram, lobster]
---

# 💬 04 · Telegram — MOC

> [!abstract] El operador habla por Telegram
> Toda la interacción humana con Lobster pasa por Telegram. El bot está construido con `aiogram v3`, soporta comandos (`/status`, `/pause`, `/think`, etc.), texto libre que dispara `CaseUse.CHAT`, y aprobaciones inline con botones (✅ Aprobar / ❌ Rechazar).

## Notas

- [[01-Bot-runner]] — ciclo de vida del bot.
- [[02-Handlers-comandos]] — tabla de comandos.
- [[03-Aprobaciones-inline]] — el flujo de aprobación con botones.
- [[04-Conversation-memory]] — memoria conversacional de 2 capas (RAM + SQLite).
- [[05-Formatting-MarkdownV2]] — escapado y conversión Markdown→MDV2.
- [[06-Notifier]] — `TelegramNotifier` para emitir mensajes desde otras partes del código.

## Comandos de un vistazo

| Comando | Qué hace |
|---|---|
| `/start` | Saludo y lista de comandos básicos |
| `/help` | Ayuda completa |
| `/status` | Modo, pendientes y última decisión |
| `/pending` | Lista de aprobaciones pendientes |
| `/show <id>` | Detalle de una aprobación |
| `/pause [razón]` | Pasa a `dry_run` |
| `/resume` | Vuelve a `normal` |
| `/kill [razón]` | Pasa a `paused` (LLM detenido) |
| `/think <q>` | Razonamiento profundo (qwen3:32b + think) |
| `/forget` | Borra el historial conversacional |
| `/toolrequests` | Lista solicitudes de herramientas pendientes |
| Texto libre | Se enruta como `CaseUse.CHAT` |

→ Ver [[../10-Operacion/02-Comandos-Telegram|Comandos Telegram operativos]] para el detalle.

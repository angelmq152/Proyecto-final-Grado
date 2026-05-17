---
title: 05 · Persistencia — MOC
tags: [moc, persistencia, sqlite, sqlmodel, alembic]
---

# 💾 05 · Persistencia — MOC

> [!abstract] Memoria larga del agente
> Lobster persiste **todo** lo que hace en una base SQLite local: cada decisión LLM, cada mutación que ejecuta, cada aprobación que pide al humano, cada turno de conversación con Telegram. Esto le permite "recordar" entre reinicios y al operador auditar sin abrir el código.

## Notas

- [[01-SQLite-esquema]] — visión global del esquema.
- [[02-Decisions]] — toda inferencia LLM.
- [[03-Actions-ledger]] — ledger de mutaciones con máquina de estados.
- [[04-Approvals]] — aprobaciones humanas con timeout.
- [[05-Tool-requests]] — herramientas que el agente pide al humano.
- [[06-Conversation-turns]] — historial chat-a-chat.
- [[07-Agent-state]] — modo global del agente.
- [[08-Events-Tenant-state-Snapshots]] — tablas auxiliares.
- [[09-Alembic-migraciones]] — versionado del esquema.

## Tablas (resumen)

| Tabla | PK | Función |
|---|---|---|
| `decisions` | UUID | Cada ciclo LLM ejecutado |
| `actions` | string-UUID | Cada mutación con estado |
| `approvals` | string-UUID | Aprobaciones pedidas al humano |
| `tool_requests` | int | Solicitudes del agente de nuevas tools |
| `conversation_turns` | int | Turnos del chat (memoria) |
| `agent_state` | id=1 | Modo único: normal/dry_run/paused |
| `events` | UUID | Eventos del sistema (uso variable) |
| `tenant_state` | UUID | Snapshots de tenants |
| `metrics_snapshots` | UUID | Snapshots de métricas |

## SQLite gotchas

> [!warning] PRAGMAs activos
> En `lobster_agent/persistence/db.py` se activan:
> - `journal_mode=WAL` — escrituras concurrentes con lecturas.
> - `synchronous=NORMAL` — buen compromiso durabilidad/rendimiento.
> - `foreign_keys=ON` — referencias `decisions ↔ actions ↔ events`.

> [!info] Ubicación de la base
> Por defecto en `/var/lib/lobster/state.db` (config `database.url=sqlite+aiosqlite:////var/lib/lobster/state.db`).

---
title: Tabla — conversation_turns
tags: [persistencia, conversacion, memoria, telegram]
---

# 💬 Tabla `conversation_turns`

> [!abstract] El historial completo de los chats
> Cada mensaje del usuario y cada respuesta del agente en Telegram se persisten aquí. La RAM en `ConversationMemory` se carga desde esta tabla al reiniciar.

## 📐 Modelo

```python
class ConversationTurn(SQLModel, table=True):
    id: int (PK auto)
    chat_id: int (indexed)
    role: str           # "user" | "assistant"
    content: str        # texto entero
    case_use: str       # "chat" | "think" | ...
    recorded_at: datetime
```

## 📋 Operaciones

```python
async def append(chat_id, role, content, case_use)
async def load_recent(chat_id, limit) -> list[ConversationTurn]   # oldest-first
async def clear(chat_id) -> None                                  # DELETE todos los del chat
```

## 🧠 RAM vs SQLite

| Aspecto | RAM | SQLite |
|---|---|---|
| Mantiene | Últimos N (default 20) por chat | Todos los turnos |
| Sobrevive a reinicio | ❌ | ✅ |
| Visible para LLM | ✅ (`get_history`) | ❌ |
| Auditoría histórica | ❌ | ✅ |
| Borrado en `/forget` | ✅ | ✅ (cascada) |

## 🔄 `warm_up(chat_id)`

> [!example] Tras un reinicio
> 1. Operador escribe en Telegram → handler llama `memory.warm_up(chat_id)`.
> 2. RAM no contiene ese chat_id → carga últimos 20 turnos.
> 3. RAM ya tiene contexto → operador no nota el reinicio.

## 🧮 Crecimiento

> [!info] Tabla pequeña pero crece
> 30 turnos/día × 365 = ~11k filas/año. Cada fila ~200 bytes → 2 MB/año. Insignificante.

> [!warning] No hay TTL automático
> Si un chat acumula 10k turnos, `load_recent(limit=20)` sigue siendo rápido (índice por `chat_id` + ORDER BY `recorded_at DESC LIMIT`). No es necesario purgar.

## 🔗 Tools que usan el historial

- `CaseUse.CHAT` → texto libre Telegram.
- `CaseUse.THINK` → `/think <q>`.
- `CaseUse.CONVERSATION` → CLI `lobster ask`.

→ Detalle en [[../04-Telegram/04-Conversation-memory]].

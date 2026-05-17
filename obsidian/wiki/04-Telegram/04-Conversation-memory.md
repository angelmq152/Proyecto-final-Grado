---
title: Telegram — Conversation memory
tags: [telegram, memoria, sliding-window, sqlite]
---

# 💭 Telegram · Conversation memory

> [!abstract] El bot recuerda lo último que dijiste
> Archivo: `lobster_agent/telegram/memory.py`. Implementación de **dos capas**: RAM (sliding window de N turnos por chat) + SQLite (`conversation_turns`, todo histórico). El LLM solo ve el RAM. El SQLite es trazabilidad y permite "calentar" la memoria tras reinicio.

## 🧬 `ConversationMemory`

```python
class ConversationMemory:
    MAX_TURNS = 20

    def __init__(self, repo_factory, max_turns: int = MAX_TURNS):
        self._cache: dict[int, list[tuple[str, str]]] = {}    # chat_id → [(role, content), ...]
        self._repo_factory = repo_factory
        self._max_turns = max_turns
```

## 🔥 `warm_up(chat_id)`

Primera vez que se accede a un chat, carga los últimos N turnos de SQLite a RAM:

```python
async def warm_up(self, chat_id):
    if chat_id in self._cache:
        return
    repo = await self._repo_factory()
    turns = await repo.load_recent(chat_id, self._max_turns)
    self._cache[chat_id] = [(t.role, t.content) for t in turns]
```

> [!tip] Sobrevive a reinicios
> Si Lobster reinicia, el primer mensaje en un chat carga el contexto previo de SQLite. El operador no nota nada.

## ➕ `append(chat_id, role, content, case_use)`

Añade a RAM (con poda a max_turns) **y** persiste a SQLite:

```python
async def append(self, chat_id, role, content, case_use):
    self._cache[chat_id].append((role, content))
    if len(self._cache[chat_id]) > self._max_turns:
        self._cache[chat_id] = self._cache[chat_id][-self._max_turns:]
    repo = await self._repo_factory()
    await repo.append(chat_id, role, content, case_use)
```

## 📤 `get_history(chat_id)` — lo que el LLM ve

```python
def get_history(self, chat_id) -> list[tuple[str, str]]:
    return list(self._cache.get(chat_id, []))
```

Lista oldest-first de tuplas `(role, content)`. Se entrega a `agent.run(message_history=...)`. Pydantic-AI lo convierte en `ModelRequest`/`ModelResponse` (ver `orchestrator._build_message_history`).

## 🗑️ `clear(chat_id)`

`/forget` en Telegram dispara:

```python
async def clear(self, chat_id):
    self._cache.pop(chat_id, None)
    repo = await self._repo_factory()
    await repo.clear(chat_id)               # DELETE FROM conversation_turns WHERE chat_id=?
```

> [!warning] Borrado total
> `clear` elimina **todas las filas** de ese chat en SQLite, no solo el cache. Es deliberado: el operador quiere empezar limpio.

## 📐 Tabla `conversation_turns`

```python
class ConversationTurn(SQLModel, table=True):
    id: int (PK auto)
    chat_id: int (indexed)
    role: str           # "user" | "assistant"
    content: str
    case_use: str       # "chat" | "think" | ...
    recorded_at: datetime
```

## 🔢 Configuración

```python
class AgentConfig(BaseModel):
    max_conversation_turns: int = 20
```

Cambiable en `config.toml`. Si subes mucho, el contexto del LLM crece → más tokens, más latencia.

## 🚦 Modos que usan memoria

| Modo | Usa memory? |
|---|---|
| `CHAT` (texto libre) | ✅ |
| `THINK` (`/think`) | ✅ |
| `CONVERSATION` | ✅ (vía CLI o aplicación externa) |
| Todos los demás (scheduler) | ❌ |

→ El scheduler **no usa memoria conversacional** porque cada job es independiente. Su "memoria" es la tabla `decisions` consultable vía `search_decisions`.

→ Sigue en [[05-Formatting-MarkdownV2]].

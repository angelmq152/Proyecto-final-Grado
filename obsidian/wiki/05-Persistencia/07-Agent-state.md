---
title: Tabla — agent_state
tags: [persistencia, agent-state, modos, sqlite]
---

# 🎚️ Tabla `agent_state`

> [!abstract] Una sola fila, mucho control
> Fila única (id=1) que guarda el modo global del agente: `normal | dry_run | paused`. Cambiar el modo aquí cambia el comportamiento de TODO el sistema (orchestrator, approval manager, scheduler).

## 📐 Modelo

```python
class AgentState(SQLModel, table=True):
    id: int = 1                          # always 1
    mode: AgentMode = AgentMode.NORMAL
    reason: str | None
    changed_at: datetime
    changed_by_user_id: int | None       # id de Telegram del operador
```

## 🔧 Repo

```python
class AgentStateRepository:
    async def get() -> AgentState:
        # autocrea si no existe (id=1, NORMAL)
    async def set_mode(mode, reason, user_id) -> AgentState
```

## 🚪 Quién cambia el modo

| Origen | Camino |
|---|---|
| Telegram `/pause`, `/resume`, `/kill` | `handlers.py` |
| Telegram tap "Pausar todo" | callback `pause_all` |
| CLI `lobster state set X` | `cli.py:set_state` |
| Test, código | `state_repo.set_mode(...)` |

## 🛡️ Quién lee el modo

| Lector | Efecto |
|---|---|
| `LobsterAgent.run` | Si `PAUSED` → cortocircuita el LLM |
| `ApprovalManager.request_approval` | Si `PAUSED` → REJECTED. Si `DRY_RUN` → auto-APPROVED |
| `/status` Telegram | Reporta el modo y emoji |

## ⏱️ Auditoría

> [!info] `changed_at` y `changed_by_user_id` se actualizan en cada set
> Esto permite saber "cuándo y quién pausó". `reason` es opcional pero recomendado.

## 🔁 Patrón "single-row" en SQLite

```python
async def get():
    state = await session.get(AgentState, 1)
    if state is None:
        state = AgentState(id=1, mode=AgentMode.NORMAL, changed_at=now)
        session.add(state); await session.commit()
    return state
```

> [!tip] Por qué id=1 fijo
> Es la forma estándar en SQLModel/SQLAlchemy de tener un singleton. Se podría usar un UNIQUE constraint en otra columna, pero esto es más simple.

→ Modos detallados en [[../02-Agente/07-Agent-state-modos]].

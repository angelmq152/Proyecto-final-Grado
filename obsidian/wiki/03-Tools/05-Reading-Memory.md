---
title: Reading — Memory tools
tags: [tools, reading, memory, decisions, sqlite]
---

# 🧠 Reading · Memoria (decisiones pasadas)

> [!abstract] El agente recuerda
> Dos tools para que el agente consulte decisiones previas, evitando repetir trabajo y permitiendo decir "ya aprobaste esto la semana pasada".

## 🛠️ `search_decisions(case_use=None, limit=10)`

> [!example] Petición
> ```text
> Tool: search_decisions
> Args: { "case_use": "alert_reactive", "limit": 20 }
> ```
> - `case_use`: filtra por modo. Si `None`, devuelve las más recientes de cualquier modo.
> - `limit`: `[1, 50]` por validación Pydantic.
>
> Devuelve `list[DecisionSummary]`.

```python
class DecisionSummary(BaseModel):
    id: str
    timestamp: datetime
    case_use: str
    prompt_summary: str         # 500 chars max
    conclusion: str             # truncada a 500
    tools_called: list[str]
```

## 🛠️ `get_decision(decision_id)`

> [!example] Detalle de una decisión
> ```text
> Tool: get_decision
> Args: { "decision_id": "550e8400-e29b-41d4-a716-446655440000" }
> ```
> Devuelve `DecisionDetail | None | ToolError` con:
>
> ```python
> reasoning: str | None        # razonamiento si think mode
> model_used: str              # qwen3:8b o qwen3:32b
> think_mode: bool
> ```

## 🔌 Bajo el capó

```python
async def search_decisions(...):
    if case_use is None:
        decisions = await decisions_repo.list_recent(limit)
    else:
        decisions = await decisions_repo.list_by_case_use(case_use, limit)
    return [_decision_summary(d) for d in decisions]
```

→ `DecisionRepository` en `persistence/repositories.py`. SQLite con índice por `timestamp` y `case_use`.

## 💡 Cómo lo usa el agente en la práctica

> [!tip] Caso real: optimization
> El prompt de `optimization` dice:
> *"Para cada candidato a scale-to-zero, comprueba el historial de decisiones: si ya fue aprobado antes, ejecuta el scale-to-zero de forma autónoma. Si es la primera vez, solicita aprobación."*
>
> El agente llama:
> 1. `search_decisions(case_use="optimization", limit=20)` — ve si ya hizo este tenant.
> 2. Si encuentra una `Decision` con `conclusion` mencionando ese namespace y `scale_to_zero`, su política interna le permite ejecutar `scale_deployment` sin pasar por aprobación.

## ⚠️ Limitación: no hay full-text search real

> [!warning] Búsqueda casefold simple
> `search_history` en `tools/memory.py` (la helper sync, no la tool registrada) hace casefold y substring sobre `prompt_summary + conclusion`. Funcional pero no escala. Para una wiki de decisiones grande haría falta FTS5 de SQLite o un índice vectorial.

→ Ver decisiones de diseño en [[../12-Decisiones-Limitaciones/03-Trade-offs#Memoria simple]].

## 🔗 Tools relacionadas

- `request_new_tool` registra carencias del propio agente. Se discute en [[09-Meta-request-new-tool]].
- `search_decisions` y `get_decision` son las únicas tools que el agente puede usar para "recordar" — el resto de tablas no se exponen como tools, son solo persistencia operativa.

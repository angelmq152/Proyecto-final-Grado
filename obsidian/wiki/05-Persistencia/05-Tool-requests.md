---
title: Tabla — tool_requests
tags: [persistencia, tool-requests, meta]
---

# 🔧 Tabla `tool_requests`

> [!abstract] El agente registra carencias
> Cuando el LLM llama a `request_new_tool(...)`, se crea una fila aquí y se notifica al operador. Es el camino que permite al agente decir *"no tengo herramienta para esto"* en lugar de inventarse una respuesta.

## 📐 Modelo

```python
class ToolRequest(SQLModel, table=True):
    id: int (PK auto)
    requested_at: datetime
    case_use: str                        # case_use vigente cuando se pidió
    user_query: str (≤500 chars)
    tool_name_suggested: str
    description: str
    suggested_inputs: str                # JSON-encoded list[str]
    status: str = "pending"              # pending | accepted | rejected | implemented
    decision_id: str | None
```

## 🚦 Status sugerido

| Status | Significado |
|---|---|
| `pending` | Nueva, sin triagar |
| `accepted` | Se implementará en un sprint próximo |
| `rejected` | No tiene sentido (out of scope) |
| `implemented` | Ya existe la tool, cerrar |

> [!warning] No hay CLI para cambiar el status hoy
> Se edita a mano en SQLite. El roadmap incluye `lobster tool-requests close <id>`.

## 📋 Inspección

```bash
uv run lobster tool-requests list
2026-05-16T12:00 get_pod_history [pending] — permite leer eventos de un pod ya borrado

# Telegram:
/toolrequests
🔧 `42` get_pod_history — permite leer eventos de un pod ya borrado
```

## 🧬 Cómo se llena

```python
ToolRequest(
    case_use=deps.current_case_use,         # "chat", "diagnose", ...
    user_query=user_query[:500],            # contexto opcional pasado por la tool
    tool_name_suggested="get_pod_history",
    description="permite leer eventos de un pod ya borrado",
    suggested_inputs=json.dumps(["namespace", "pod_name"]),
)
```

## 💡 Para qué sirve realmente

> [!tip] Backlog de producto sin salir del producto
> En lugar de pedir al operador que abra un ticket en GitHub, el agente lo registra él mismo. Ideal cuando estás conversando por Telegram y el agente dice *"para responder a eso necesitaría una tool nueva (id=42)"*. Cierras el chat sabiendo que está anotado.

→ Tool fuente: [[../03-Tools/09-Meta-request-new-tool]].

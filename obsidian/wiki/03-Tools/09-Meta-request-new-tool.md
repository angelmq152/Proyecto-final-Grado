---
title: Meta — request_new_tool
tags: [tools, meta, tool-request, autoreflexion]
---

# 🔧 Meta · `request_new_tool`

> [!abstract] El agente puede pedir herramientas que no tiene
> Archivo: `lobster_agent/agent/tools/meta.py`. Cuando el LLM se da cuenta de que necesita algo que no tiene (p.ej. "obtener los logs históricos de un pod borrado"), llama esta tool. Eso crea una fila en `tool_requests` y manda mensaje al operador.

## 🛠️ Firma

```python
async def request_new_tool(
    ctx: RunContext[AgentDeps],
    tool_name_suggested: str,
    description: str,
    suggested_inputs: list[str],
    user_query: str = "",
) -> str
```

## 📝 Comportamiento

1. Inserta `ToolRequest` en `tool_requests`:
   ```python
   ToolRequest(
       case_use=deps.current_case_use,
       user_query=user_query[:500],
       tool_name_suggested="get_pod_history",
       description="permite leer eventos de un pod ya borrado",
       suggested_inputs=json.dumps(["namespace", "pod_name"]),
       status="pending",
   )
   ```
2. Envía mensaje a Telegram:
   ```
   🔧 *Nueva solicitud de herramienta:* `get_pod_history`
   permite leer eventos de un pod ya borrado
   ```
3. Devuelve al LLM: `"Solicitud registrada (id=42). El operador será notificado."`.

## 🧭 Cuándo se usa

> [!example] Caso típico
> Operador en Telegram: *"Lobster, ¿cuánta RAM media gasta el tenant tenant-acme la última semana?"*
> Agente: *"No tengo una tool para series semanales agregadas por namespace. He registrado la petición (id=14)."*

> [!tip] Heurística desde prompt
> El bloque común de principios incluye:
> *"Si no tienes la herramienta necesaria, llama a request_new_tool para registrar la carencia."*

## 📋 Estado de las solicitudes

```python
class ToolRequest(SQLModel, table=True):
    id: int (PK)
    requested_at: datetime
    case_use: str
    user_query: str (≤500)
    tool_name_suggested: str
    description: str
    suggested_inputs: str    # JSON-encoded list[str]
    status: str = "pending"  # pending | accepted | rejected | implemented
    decision_id: str | None
```

## 👁️ Ver y triagar

- **CLI**: `uv run lobster tool-requests list [--status pending] [--limit 20]`
- **Telegram**: `/toolrequests` muestra las 10 últimas pendientes.

## 🚏 Estados sugeridos (futuro)

> [!warning] Hoy no hay handler para cambiar el status
> El campo `status` existe pero no hay CLI ni UI para cambiarlo a `implemented`. Se hace a mano editando la DB. El roadmap incluye `lobster tool-requests close <id>` y `--implemented-as <commit>`.

→ Ver [[../12-Decisiones-Limitaciones/05-Futuro-roadmap#Triaje de tool_requests]].

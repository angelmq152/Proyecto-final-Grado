---
title: Tabla — decisions
tags: [persistencia, decisions, sqlite, decisionrepository]
---

# 🧾 Tabla `decisions`

> [!abstract] Una fila por ciclo LLM
> Cada vez que `LobsterAgent.run()` se ejecuta — exitoso, fallido, o skipped por modo paused — se persiste una `Decision`.

## 📐 Modelo

```python
class Decision(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    timestamp: datetime = Field(default_factory=utc_now, index=True)
    trigger: str = Field(default="manual", index=True)
    case_use: str = Field(index=True)
    model_used: str
    think_mode: bool
    prompt_summary: str            # truncado a 500
    reasoning: str | None
    conclusion: str
    tokens_input: int = 0
    tokens_output: int = 0
    latency_ms: int = 0
    tools_called: list[str] = Field(sa_column=Column(JSON))
    derived_actions: list[str] = Field(sa_column=Column(JSON))
```

## 🔍 Operaciones (DecisionRepository)

```python
class DecisionRepository:
    async def save(decision) -> Decision
    async def get_by_id(decision_id: UUID) -> Decision | None
    async def list_recent(limit=10) -> list[Decision]
    async def list_by_case_use(case_use, limit=10) -> list[Decision]
```

## 🧮 Qué se persiste, con qué granularidad

| Campo | Origen | Ejemplo |
|---|---|---|
| `timestamp` | `datetime.now(UTC)` en `run()` | `2026-05-16T14:32:00Z` |
| `case_use` | `CaseUse.value` | `health_loop_read` |
| `model_used` | `select_model(case_use)` | `qwen3:8b` |
| `think_mode` | `use_think_mode(case_use)` | `False` |
| `prompt_summary` | `user_input[:500]` | `"Ejecuta health check rápido..."` |
| `conclusion` | `result.output` (string) | `"[OK] Todo saludable."` |
| `tokens_input` | `result.usage().input_tokens` | `3421` |
| `tokens_output` | `result.usage().output_tokens` | `212` |
| `latency_ms` | `(end-start).total_seconds()*1000` | `12450` |
| `tools_called` | `_tools_called_from_messages` | `["list_pods", "get_node_health"]` |
| `derived_actions` | reservado (no usado hoy) | `[]` |
| `reasoning` | None hoy (think mode no llena este campo aún) | `None` |

## 🚦 Outcomes en métricas, NO en la fila

> [!warning] No hay columna `outcome`
> Aunque `AgentResult.outcome` toma valores `success | failed | skipped_paused`, eso se va a la métrica `lobster_decisions_total` pero **no a la fila**. La fila guarda la conclusión completa. Por tanto si `outcome=failed`, `conclusion` contiene el error.

## 📋 Inspección operativa

```bash
uv run lobster decisions list --limit 20
2026-05-16T14:32:00 ab12cd34-…  health_loop_read qwen3:8b think=False latency_ms=12450
  [OK] Todo saludable.
```

Con `--show-reasoning` añade el `reasoning` si lo hay.

## 🧠 Cómo lo usa el agente

El agente **se consulta a sí mismo** vía las tools `search_decisions` y `get_decision`:
- Para evitar repetir consejos ya dados.
- Para detectar "este scale-to-zero ya fue aprobado antes".
- Para auditar tras incidencias.

→ Ver [[../03-Tools/05-Reading-Memory]].

## ⚖️ Volumen esperado

> [!info] Crecimiento
> - `health_loop` cada 5 min → ~288 filas/día.
> - `global_state` cada 30 min → ~48 filas/día.
> - `hourly_summary` → 24 filas/día.
> - `daily_summary` → 1 fila/día.
> - `alert_reactive` → variable (típico 5-30 filas/día).
> - Conversación (chat) → variable.
>
> **Total**: ~350-500 filas/día. A 1 KB cada una (conclusion media), eso son ~150 MB/año.

→ Considera VACUUM periódico si tu disco aprieta. En homelab con disco generoso, no es necesario.

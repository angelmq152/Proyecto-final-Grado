---
title: Operación — Modos normal / dry_run / paused
tags: [operacion, modos, agent-state]
---

# 🚦 Modos del agente

> [!abstract] Tres palancas, tres usos
> Una sola fila en `agent_state` define el modo global. Esta nota explica **cuándo usar cada uno**.

## 🟢 `normal` — comportamiento estándar

> [!info] Por defecto
> - LLM se ejecuta.
> - Aprobaciones se piden al humano.
> - Mutaciones reales tras aprobación.

## 🟡 `dry_run` — ensayo controlado

> [!info] Para probar
> - LLM se ejecuta.
> - **Aprobaciones se auto-aprueban** con `reason="dry_run_auto_approved"` (no se envían a Telegram).
> - **Mutaciones se simulan** si `agent.dry_run_default=True` → estado `ABORTED_DRY_RUN`.

> [!warning] `dry_run` global ≠ `dry_run_default` del flag
> - **Mode `dry_run`**: afecta a aprobaciones (auto-approved).
> - **`dry_run_default=True`** en config: afecta a executor (abort antes de tocar K8s).
>
> Para una sesión de pruebas "sin pedir aprobación y sin ejecutar":
> 1. `state set dry_run`.
> 2. `dry_run_default = true` en `[agent]` config.
> 3. Reiniciar Lobster.

> [!example] Caso típico
> Probar un cambio en prompts sin riesgo. El agente razonará y propondrá acciones, pero todas se anotarán en `actions` como `ABORTED_DRY_RUN`. Buena para validar UX antes de soltar.

## 🔴 `paused` — todo parado

> [!info] Para incidentes
> - **LLM NO se ejecuta**. `LobsterAgent.run()` devuelve `outcome="skipped_paused"`.
> - Nuevas aprobaciones se crean ya `REJECTED` con `reason="agent_paused"`.
> - Las aprobaciones ya pendientes siguen su curso (expiran si no se atienden).
> - Scheduler sigue disparando jobs, pero al llamar a `agent.run` se cortocircuita.

> [!warning] No para el scheduler
> El scheduler/watcher siguen vivos. Solo el LLM se "duerme". Esto ahorra coste GPU y evita que el agente actúe sobre infra rota.

> [!example] Cuándo usar
> - Ollama caído → `state set paused`. Mientras tanto Lobster sigue contando métricas y respondiendo `/status` por Telegram.
> - Mantenimiento del clúster → `state set paused`, haces el cambio, `state set normal`.

## 🔄 Cambio de modo

| Camino | Cómo |
|---|---|
| CLI | `uv run lobster state set normal\|dry_run\|paused [--reason "x"]` |
| Telegram | `/pause [r]`, `/resume`, `/kill [r]` |
| Botón inline | "Pausar todo" en una aprobación → `dry_run` |

## 📊 Métricas afectadas

| Modo | `lobster_decisions_total` |
|---|---|
| `normal` | outcome=success/failed |
| `dry_run` | outcome=success/failed (igual) |
| `paused` | outcome=skipped_paused |

> [!tip] Detectar pausado en métricas
> ```promql
> sum(rate(lobster_decisions_total{outcome="skipped_paused"}[5m]))
> ```
> Si > 0, el agente está pausado. Útil para alertar si alguien lo dejó pausado más de lo previsto.

## 🧭 Auditoría

```bash
uv run lobster state get
# normal changed_at=2026-05-15T22:18:43+00:00 reason=-

# o ver el histórico (si lleva tiempo):
sqlite3 /var/lib/lobster/state.db \
  "SELECT changed_at, mode, reason, changed_by_user_id FROM agent_state;"
```

> [!warning] Single row, no histórico nativo
> La tabla `agent_state` siempre tiene 1 fila. Para histórico de cambios habría que añadir una tabla `agent_state_log`. Roadmap.

→ Ver [[../02-Agente/07-Agent-state-modos]] para el detalle técnico.

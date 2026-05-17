---
title: CaseUse y routing
tags: [agente, caseuse, routing, modos]
---

# 🚦 `CaseUse` y routing

> [!abstract] 14 modos distintos del agente
> `lobster_agent/agent/routing.py` define `CaseUse` (StrEnum) y dos funciones puras: `select_model(case_use)` y `use_think_mode(case_use)`. La combinación de las tres decide cómo se comporta el LLM en cada disparo.

## 📜 Los 14 modos

| Modo | Significado | Disparado por |
|---|---|---|
| `SMOKE_TEST` | Solo herramientas dummy | Tests |
| `HEALTH_LOOP_READ` | Lectura periódica sin actuar | Scheduler (cada 5 min) |
| `HEALTH_LOOP_ANALYZE` | Tras `[ANOMALÍA]` o K8s watcher, decide y actúa | Scheduler chain / Watcher |
| `GLOBAL_STATE` | Snapshot global cada 30 min | Scheduler |
| `OPTIMIZATION` | Razona sobre scale-to-zero | Scheduler (3:00 AM) |
| `ONBOARDING` | Alta guiada de un tenant | Operador |
| `DIAGNOSE` | Diagnóstico profundo | Operador |
| `SUMMARY` | Resumen horario corto | Scheduler (`0 * * * *`) |
| `DAILY_SUMMARY` | Informe completo en Markdown → Obsidian | Scheduler (8:00 AM) |
| `BACKUP` | Razona estado backups | Scheduler (2:00 AM) |
| `ALERT_REACTIVE` | Reacción a webhook Alertmanager | `/webhook/alert` |
| `CONVERSATION` | Operador hace preguntas largas | Operador |
| `CHAT` | Operador en Telegram (texto libre) | Telegram |
| `THINK` | `/think <q>` profundo | Telegram |

## 🎯 `select_model()`

```python
def select_model(case_use: CaseUse) -> str:
    return {
        CaseUse.SMOKE_TEST: "qwen3:8b",
        CaseUse.HEALTH_LOOP_READ: "qwen3:8b",
        CaseUse.HEALTH_LOOP_ANALYZE: "qwen3:8b",
        CaseUse.GLOBAL_STATE: "qwen3:8b",
        CaseUse.OPTIMIZATION: "qwen3:8b",
        CaseUse.ONBOARDING: "qwen3:32b",
        CaseUse.DIAGNOSE: "qwen3:32b",
        CaseUse.SUMMARY: "qwen3:8b",
        CaseUse.DAILY_SUMMARY: "qwen3:32b",
        CaseUse.BACKUP: "qwen3:8b",
        CaseUse.ALERT_REACTIVE: "qwen3:8b",
        CaseUse.CONVERSATION: "qwen3:32b",
        CaseUse.CHAT: "qwen3:8b",
        CaseUse.THINK: "qwen3:32b",
    }[case_use]
```

> [!tip] Heurística operativa
> - **qwen3:8b** para todo lo que se ejecuta frecuente o reactivo (health_loop, alert_reactive). Cabe en VRAM rápido (~30 s/respuesta).
> - **qwen3:32b** para análisis profundo o textos largos (DAILY_SUMMARY, CONVERSATION, ONBOARDING, DIAGNOSE, THINK). Tarda minutos pero produce informe legible.

## 🧠 `use_think_mode()`

```python
def use_think_mode(case_use: CaseUse) -> bool:
    return case_use not in {
        CaseUse.SMOKE_TEST,
        CaseUse.HEALTH_LOOP_READ,
        CaseUse.HEALTH_LOOP_ANALYZE,
        CaseUse.SUMMARY,
        CaseUse.DAILY_SUMMARY,
        CaseUse.BACKUP,
        CaseUse.ALERT_REACTIVE,
        CaseUse.CHAT,
    }
```

> [!warning] Por qué se desactiva think en mutaciones
> El comentario del código lo dice claro:
> *"Think mode (Qwen3 /think) suele causar que el modelo emita los tool calls como texto (p.ej. `<tools>...</tools>`) en lugar de invocarlos. Por eso lo desactivamos en `daily_summary` (commit 5ff8e13) y aquí también en los modos que deben ejecutar mutaciones de forma fiable: `HEALTH_LOOP_ANALYZE` (autónomo en CrashLoopBackOff) y `ALERT_REACTIVE` (reacciona a alertas reales)."*

→ Más sobre el problema en [[../11-Modelos-IA/03-Think-mode]] y [[../11-Modelos-IA/05-Tool-calling]].

## 🧮 Matriz definitiva modelo × think

| CaseUse | Modelo | Think | Razón |
|---|---|---|---|
| SMOKE_TEST | 8b | ❌ | Solo dummy tools |
| HEALTH_LOOP_READ | 8b | ❌ | Lectura corta y crítica, sin razonamiento |
| HEALTH_LOOP_ANALYZE | 8b | ❌ | Mutaciones reales — think rompe tool calls |
| GLOBAL_STATE | 8b | ✅ | Análisis sin mutar |
| OPTIMIZATION | 8b | ✅ | Razonamiento sobre scale-to-zero |
| ONBOARDING | 32b | ✅ | Diálogo complejo |
| DIAGNOSE | 32b | ✅ | Diagnóstico profundo |
| SUMMARY | 8b | ❌ | Resumen rápido |
| DAILY_SUMMARY | 32b | ❌ | 10 tool calls, calidad textual |
| BACKUP | 8b | ❌ | Razonamiento corto |
| ALERT_REACTIVE | 8b | ❌ | Mutaciones reales |
| CONVERSATION | 32b | ✅ | Operador haciendo preguntas |
| CHAT | 8b | ❌ | Conciso y rápido |
| THINK | 32b | ✅ | Razonamiento explícito pedido |

## ➕ Cómo añadir un nuevo CaseUse

> [!example] Receta
> 1. Añadir el valor al enum en `lobster_agent/agent/routing.py`.
> 2. Añadir entrada en `select_model()` y considerar `use_think_mode()`.
> 3. Añadir entrada en `_MISSIONS` en `lobster_agent/agent/prompts/system.py`.
> 4. Añadir entrada en `_build_tools_for_case()` en `orchestrator.py` con la lista de tools permitidas.
> 5. Definir el disparador (scheduler / webhook / handler).
> 6. Test en `tests/test_routing.py`.

→ Continúa en [[03-Modelos-Qwen3]] para entender qué modelo usar.

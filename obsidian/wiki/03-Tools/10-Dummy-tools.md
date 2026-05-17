---
title: Dummy tools
tags: [tools, dummy, smoke-test, debug]
---

# 🧪 Dummy tools

> [!abstract] Tools de depuración
> Archivo: `lobster_agent/agent/tools/dummy.py`. Se usan en `CaseUse.SMOKE_TEST` y cuando `settings.agent.enable_dummy_tools = True`. Sirven para validar el camino Pydantic-AI → Ollama → tool call → respuesta sin tocar nada real.

## 🛠️ Tools registradas

| Tool | Qué hace |
|---|---|
| `get_time()` | Devuelve `datetime.now().isoformat()` |
| `echo(text)` | Devuelve el mismo texto |
| `simple_calc(expression)` | Evalúa una expresión aritmética básica |

## 🚦 Cuándo se cargan

```python
if no_tools or case_use == CaseUse.SMOKE_TEST or enable_dummy_tools or deps is None:
    return [get_time, echo, simple_calc]
```

## 🧪 Uso desde tests

```python
agent = LobsterAgent(settings, deps=None, no_tools=True)
result = await agent.run(CaseUse.SMOKE_TEST, "qué hora es?")
assert "T" in result.data  # ISO timestamp
```

## 🧰 CLI flag para forzar

```bash
uv run lobster ask "calcula 2+2" --no-tools
```

Eso fuerza `no_tools=True` y solo registra dummies, ignorando todo el resto.

## 📌 Por qué existen

> [!tip] Validar el pipeline sin tocar la infra
> Cuando se actualiza Pydantic-AI o Ollama, el primer test es: *"sigue siendo capaz de llamar `get_time` correctamente?"*. Si eso falla, el problema es del binding LLM, no del clúster.

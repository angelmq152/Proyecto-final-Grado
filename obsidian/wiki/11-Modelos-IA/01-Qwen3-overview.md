---
title: Qwen3 — Overview
tags: [llm, qwen3, modelos, ollama]
---

# 🧬 Qwen3 — Overview

> [!abstract] Una sola familia, dos talles
> Qwen3 es la familia de modelos LLM de Alibaba (Tongyi Lab) lanzada en 2025. Lobster usa dos talles: 8B (rápido) y 32B (calidad). Ambos servidos por Ollama local.

## 🏢 ¿Qué es Qwen3?

- LLM de uso general, multilingüe (≥30 idiomas), entrenado con RLHF.
- Soporta **tool calling** nativo en el formato OpenAI.
- Soporta una extensión propietaria llamada **`/think`** (think mode) que añade una fase de razonamiento explícito antes de la respuesta.
- Distribuido en GGUF para inferencia local con Ollama / llama.cpp.

## 🎯 Versiones usadas

| Modelo | Tamaño | VRAM aprox | Velocidad LeIA |
|---|---|---|---|
| `qwen3:8b` | 8B params | ~10 GB | 10-40 s típico |
| `qwen3:32b` | 32B params | ~24-26 GB | 1-8 min típico |

## 🔌 Endpoint Ollama

```python
class OllamaConfig:
    base_url = "http://localhost:11434/v1"      # OpenAI-compatible
    api_key  = "ollama"                          # cualquier valor
    timeout_seconds = 180.0                      # default; override por modelo
```

## 🧠 Capacidades aprovechadas

- **Tool calling**: el LLM emite JSON estructurado con `tool_calls` que Pydantic-AI interpreta.
- **Streaming**: tanto la respuesta como (con think) el razonamiento se streamean.
- **System prompt en español**: Qwen3 funciona muy bien en español.

## 🚫 Limitaciones observadas

- **Think mode + tool calls** → conflicto: el modelo a veces emite el tool call como texto literal `<tools>{...}</tools>` en lugar de invocarlo.
- **Latencia 32B** → para usos interactivos (Telegram) es demasiado lento sin streaming, por eso CHAT usa 8B.
- **Hallucinations en nombres** → el modelo inventa nombres de pod/deployment si no verifica con tools. El prompt explícito previene esto.

## 🛠️ Tool calling internals

Cuando el LLM decide llamar una tool, emite:

```json
{
  "tool_calls": [
    {
      "id": "call_abc",
      "type": "function",
      "function": {
        "name": "list_pods",
        "arguments": "{\"namespace\":\"tenant-acme\"}"
      }
    }
  ]
}
```

Pydantic-AI:
1. Parsea el `tool_calls`.
2. Ejecuta la función registrada con los args.
3. Devuelve el resultado al LLM en el siguiente turno como `role=tool`.
4. El LLM puede llamar más tools o producir la respuesta final.

→ Detalle en [[05-Tool-calling]].

## 📚 Recursos externos

- **Qwen3 docs**: https://qwenlm.github.io/blog/qwen3
- **Ollama Qwen3**: https://ollama.com/library/qwen3
- **Pydantic-AI**: https://ai.pydantic.dev/

→ Comparativa de talles en [[02-8b-vs-32b]].

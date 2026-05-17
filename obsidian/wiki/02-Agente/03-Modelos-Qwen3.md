---
title: Modelos Qwen3 — 8b vs 32b vs think
tags: [agente, qwen3, modelos, ollama]
---

# 🧬 Modelos Qwen3 — 8b · 32b · think

> [!abstract] Dos modelos, un servidor
> Ambos modelos viven en el **mismo Ollama local** (`http://localhost:11434/v1`) corriendo en LeIA. Su selección se hace en runtime por `CaseUse`. Esta nota explica capacidades, costes y trampas.

## 📊 Tabla comparativa

| Característica | `qwen3:8b` | `qwen3:32b` |
|---|---|---|
| Tamaño | 8B parámetros | 32B parámetros |
| VRAM aprox | ~10 GB | ~24-26 GB |
| Tiempo medio por respuesta | 10-40 s | 1-8 min |
| Calidad textual | Buena | Excelente |
| Razonamiento sobre tool calls | Sólido | Sólido |
| Coste de cambio en Ollama | bajo si está cargado | alto (descarga otro) |
| Modos donde se usa | health, summary, chat, alert | daily, conversation, think, onboarding, diagnose |

## 🧠 Think mode (`/think` de Qwen3)

Qwen3 soporta un modo "thinking" que añade una fase de razonamiento explícito antes de la respuesta. Se activa pasando `extra_body={"think": True}` en `ModelSettings` (lo hace `LobsterAgent._build_model`).

> [!warning] Bug observado en producción
> Con `think=True`, Qwen3 a veces emite los tool calls como **texto literal** (`<tools>{"name":"restart_pod",...}</tools>`) en lugar de invocarlos como tool calls reales del protocolo OpenAI. Eso significa que la herramienta **no se ejecuta** — solo aparece como texto en la respuesta.
>
> Por eso Lobster desactiva think en `HEALTH_LOOP_ANALYZE`, `ALERT_REACTIVE` y `DAILY_SUMMARY`. Los system prompts incluyen además la regla explícita:
> ```
> Prohibido escribir tool calls como texto (p.ej. <tools>{"name":"restart_deployment",...}</tools>).
> ```

→ Análisis completo en [[../11-Modelos-IA/03-Think-mode]].

## ⚙️ Configuración de Ollama desde Lobster

```python
class OllamaConfig(BaseModel):
    base_url: str = "http://localhost:11434/v1"
    api_key: str = "ollama"          # Ollama acepta cualquier valor
    timeout_seconds: float = 180.0
```

> [!info] Por qué el endpoint termina en `/v1`
> Ollama expone un endpoint **OpenAI-compatible** en `/v1/chat/completions`. Pydantic-AI usa `OpenAIChatModel` con un `OpenAIProvider(base_url=..., api_key=...)`. Esto permite cambiar a OpenAI/Anthropic con solo cambiar la URL.

## 🚏 Cuándo usar cada uno (regla simple)

> [!tip] Heurística operativa
> - **Si el modo tiene que actuar (mutación) o ser rápido → 8b sin think.**
> - **Si el modo tiene que producir un informe legible o razonar profundamente → 32b.**
> - **Si el modo razona sin tools → considera think.**
> - **Si el modo razona con tools → desactiva think.**

## 💸 Coste de switch

> [!warning] Ollama serializa modelos
> Si el modelo cargado es `qwen3:8b` y llega una petición a `qwen3:32b`, Ollama descarga uno y carga otro. Eso son ~8 s perdidos. La **Fase 9** introdujo la cola FIFO precisamente para evitar el ping-pong (8b ↔ 32b ↔ 8b) que sucedía con jobs solapados.
>
> → Ver [[../07-Scheduler-Watcher/07-Job-queue-fase9]] y [[../11-Modelos-IA/06-Timeouts-y-cola]].

## 🧪 Latencia LLM observada

> [!example] Medida desde la métrica `lobster_llm_latency_seconds`
> Buckets del histograma: `1, 2, 5, 10, 20, 30, 60, 120, 180, 300, 600`.
>
> Valores reales típicos en LeIA con GPU consumer:
> - `qwen3:8b` sin think → p50 ≈ 12 s, p95 ≈ 35 s.
> - `qwen3:8b` con think → p50 ≈ 90 s, p95 ≈ 240 s.
> - `qwen3:32b` sin think → p50 ≈ 180 s, p95 ≈ 480 s.
> - `qwen3:32b` con think → p50 ≈ 400 s, p95 ≈ 800 s.

## 🔄 Cache de agentes Pydantic-AI

`LobsterAgent._agents` es un `dict[(case_use, model, think), Agent]`. Cada combinación se construye solo una vez. Esto evita reinstanciar el `Agent` y revalidar las tools en cada `run()`.

> [!info] Cache no incluye Ollama
> El cache es solo de la pieza Pydantic-AI. Ollama mantiene su propio cache de modelos cargados. Una request con `qwen3:8b` reusará el binding aunque Ollama tenga que recargar el modelo si se ha descargado.

→ Sigue en [[04-System-prompts]].

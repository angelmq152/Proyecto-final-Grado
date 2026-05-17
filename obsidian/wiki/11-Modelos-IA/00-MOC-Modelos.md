---
title: 11 · Modelos IA — MOC
tags: [moc, llm, qwen3, ollama, pydantic-ai]
---

# 🧬 11 · Modelos IA — MOC

> [!abstract] Qwen3 + Ollama + Pydantic-AI
> Lobster es agnóstico al modelo pero está sintonizado para **Qwen3** corriendo sobre **Ollama** local. Usa el API "OpenAI-compatible" de Ollama vía la integración `OpenAIChatModel` de Pydantic-AI. Dos modelos: `qwen3:8b` (rápido, casi todos los modos) y `qwen3:32b` (lento, daily_summary y razonamientos profundos). El "think mode" de Qwen3 se activa solo donde aporta valor — y se desactiva en mutaciones porque el modelo a veces emite tool calls como texto en lugar de invocarlas.

## Notas

- [[01-Qwen3-overview]] — el modelo, sus capacidades y formato.
- [[02-8b-vs-32b]] — diferencias y cuándo usa cada uno.
- [[03-Think-mode]] — qué es `/think`, ventajas, problemas reales.
- [[04-Pydantic-AI]] — la librería que orquesta tool calling.
- [[05-Tool-calling]] — formato, retries, errores típicos.
- [[06-Timeouts-y-cola]] — timeouts dinámicos por modelo, cola Fase 9.
- [[07-Limitaciones-y-mitigaciones]] — qué falla y cómo se compensa.

## Tabla por CaseUse

| CaseUse | Modelo | Think | Razón |
|---|---|---|---|
| SMOKE_TEST | qwen3:8b | ❌ | Sólo dummy tools |
| HEALTH_LOOP_READ | qwen3:8b | ❌ | Lectura corta y crítica |
| HEALTH_LOOP_ANALYZE | qwen3:8b | ❌ | Debe ejecutar mutaciones; think rompe tool calls |
| GLOBAL_STATE | qwen3:8b | ✅ | Análisis amplio sin mutar |
| OPTIMIZATION | qwen3:8b | ✅ | Razonamiento sobre scale-to-zero |
| ONBOARDING | qwen3:32b | ✅ | Guiado complejo |
| DIAGNOSE | qwen3:32b | ✅ | Diagnóstico profundo |
| SUMMARY | qwen3:8b | ❌ | Resumen rápido |
| DAILY_SUMMARY | qwen3:32b | ❌ | Mejor calidad textual sin think (think falla en tool calls) |
| BACKUP | qwen3:8b | ❌ | Razona sobre tier sin actuar |
| ALERT_REACTIVE | qwen3:8b | ❌ | Mutaciones reales |
| CONVERSATION | qwen3:32b | ✅ | Operador haciendo preguntas |
| CHAT | qwen3:8b | ❌ | Rápido y conciso |
| THINK | qwen3:32b | ✅ | Razonamiento explícito pedido por el operador |

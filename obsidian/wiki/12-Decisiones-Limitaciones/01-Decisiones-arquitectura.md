---
title: Decisiones de arquitectura
tags: [decisiones, arquitectura, tfg, academico]
---

# 🧭 Decisiones de arquitectura

> [!abstract] Capítulo académico
> Las decisiones grandes del proyecto, con su justificación. Esta nota es el "ADR consolidado" — Architecture Decision Records resumidos en uno.

## ADR-001 — LLM local (Ollama) en lugar de API en la nube

> [!info] Decisión
> Toda la inferencia LLM corre en **Ollama local en LeIA**. No se usa la API de Anthropic ni OpenAI.

**Alternativas consideradas**:
- API Anthropic (Claude) → mejor calidad pero coste continuo y dependencia de red.
- API OpenAI → mismo problema.
- llama.cpp standalone → más control pero más complejidad operativa.

**Por qué Ollama**:
1. **Privacidad**: el TFG es un homelab personal; no se quiere enviar nombres de tenant a un proveedor cloud.
2. **Coste cero**: ya tengo GPU.
3. **Demostración técnica**: el TFG demuestra que un LLM local puede orquestar infra real.
4. **Resiliencia**: si internet cae, el agente sigue funcionando.

**Coste asumido**: latencia más alta que cloud, menos calidad que Claude/GPT-4.

## ADR-002 — Qwen3 como familia de modelos

> [!info] Decisión
> Qwen3 (8B y 32B) en lugar de Llama 3, Mistral, Phi-4, etc.

**Por qué Qwen3**:
- Excelente español (importante para prompts y respuestas).
- Tool calling estable en formato OpenAI-compatible.
- Tamaños que caben en GPU consumer.
- Licencia permisiva (Apache 2.0).
- Modo `/think` que aporta calidad cuando se necesita.

**Trade-off identificado**: el think mode tiene el bug de emitir tool calls como texto → solución: desactivarlo en mutaciones (ver [[../11-Modelos-IA/03-Think-mode]]).

## ADR-003 — Pydantic-AI como framework agéntico

> [!info] Decisión
> Pydantic-AI en lugar de LangChain, LlamaIndex, AutoGen.

**Por qué Pydantic-AI**:
1. **Minimalista**: ~3 dependencias core.
2. **Tipado fuerte**: las tools son funciones Python tipadas; el schema sale solo.
3. **Async-nativo**: encaja con FastAPI + APScheduler.
4. **Sin "magic"**: el flujo del run es legible en 300 líneas.

**Descartado LangChain**: demasiadas abstracciones, muchas deps, breaking changes frecuentes.

## ADR-004 — SQLite + SQLModel para persistencia

> [!info] Decisión
> SQLite local con SQLModel (= SQLAlchemy + Pydantic). No Postgres.

**Por qué**:
- Homelab personal, sin red para DB dedicada.
- 9 tablas con < 1 M filas en horizonte de años.
- WAL mode da concurrencia suficiente.
- El agente debe sobrevivir a caída del clúster que monitoriza → DB local.

**Trade-off**: no escala a multi-instancia. Pero el TFG es single-instance.

## ADR-005 — APScheduler en proceso en lugar de cron

> [!info] Decisión
> APScheduler dentro del proceso FastAPI, no cron del SO.

**Por qué**:
- Necesitamos llamar funciones Python in-process con timeouts.
- Mismo runtime async; sin overhead de fork.
- Reusar conexiones HTTP a Ollama / Prom / Loki.
- Métricas Prom dentro del mismo proceso.

**Descartado**: cron + scripts CLI separados — habría requerido gestionar conexiones múltiples, autenticación duplicada, etc.

## ADR-006 — Telegram como UI principal

> [!info] Decisión
> Telegram aiogram v3, no Slack ni web UI propia.

**Por qué**:
- Operador (yo) ya tiene Telegram en móvil y desktop.
- Bot tokens gratis y permanentes.
- Soporte de botones inline ideal para aprobaciones.
- No expone puertos HTTPS al exterior (polling).

**Trade-off**: dependiente de Telegram BV. Aceptable para un TFG personal.

## ADR-007 — RBAC mínimo + policy en código

> [!info] Decisión
> Dos capas independientes:
> 1. RBAC K8s con verbos limitados.
> 2. `domain/policy.py` con allowlist y kinds prohibidos.

**Por qué doble defensa**:
- Un bug en una capa no compromete la otra.
- La policy del código es testeable unitariamente.
- El RBAC protege incluso si Lobster se hackea.

→ [[../08-Infraestructura/05-RBAC-Kubeconfig]] y [[../09-Tenants/06-Politica-namespaces]].

## ADR-008 — Aprobaciones humanas bloqueantes

> [!info] Decisión
> `MutationContext` espera **bloqueando** (con poll a SQLite cada 1s) hasta que la aprobación se resuelve.

**Alternativa considerada**: estilo "command pattern" — el agente delega y vuelve después. Más complejo.

**Por qué bloqueante**:
- Mantiene el flujo lineal del LLM.
- Pydantic-AI no soporta paussand y resume nativamente.
- Polling 1s sobre SQLite es eficiente (~10 KB/s).
- En `paused` el agente no actúa, así que no hay bloqueo perpetuo.

**Trade-off**: si la aprobación tarda 30 min, el agente está "ocupado" 30 min. Mitigado con la cola FIFO de Fase 9.

## ADR-009 — Cola FIFO sin priorización

> [!info] Decisión (Fase 9)
> Cola simple FIFO con un único worker. No hay prioridades.

**Por qué simple**:
- La complejidad de priority queue introduce bugs (starvation).
- `health_loop_read` corre **fuera** de la cola (es el único crítico-rápido).
- El watcher dispara directo al agente.
- En la práctica el daily_summary y alert_reactive raramente compiten.

**Si fuera problema**: roadmap incluye `PriorityJobQueue`.

## ADR-010 — Resúmenes diarios al vault Obsidian

> [!info] Decisión
> El daily_summary se guarda como Markdown en `obsidian/YYYY-MM/`, no en SQLite ni en Loki.

**Por qué**:
- El vault Obsidian es donde el operador ya lleva sus notas.
- El plain Markdown sobrevive a cambios de software.
- Grep / búsqueda full-text inmediatas.
- Renderizado en Obsidian con tablas, código, emojis.

## ADR-011 — Prompts en español

> [!info] Decisión
> Misiones y reglas de los prompts están en español. Algunas reglas técnicas (tool calls antianulación) están en inglés.

**Por qué**:
- El operador habla español → respuestas más naturales.
- Qwen3 razona bien en español.
- Reglas en inglés cuando el LLM "aprende mejor" la regla en su idioma de entrenamiento original.

→ Continúa en [[02-Limitaciones-actuales]].

---
title: Think mode — /think de Qwen3
tags: [llm, qwen3, think, razonamiento]
---

# 💭 Think mode (`/think` de Qwen3)

> [!abstract] Razonar antes de responder
> Qwen3 soporta una extensión propietaria donde, antes de la respuesta final, el modelo emite un bloque de razonamiento visible. Aumenta calidad pero penaliza tool calling.

## 🧬 Cómo se activa

```python
# orchestrator._build_model
settings = ModelSettings(
    timeout=timeout,
    extra_body={"think": think},          # ← bool
)
return OpenAIChatModel(model_name, provider=provider, settings=settings)
```

`extra_body` se propaga a Ollama, que lo entiende como hint al modelo.

## ⏱️ Coste

> [!info] Think aumenta latencia 2-5x
> El modelo dedica ~50-80% del tiempo al razonamiento antes de responder. Por eso `_build_model` desactiva el read timeout cuando think está activo:
> ```python
> if think:
>     timeout = httpx.Timeout(None, connect=30.0)    # sin read timeout
> ```

## 🚦 Quién usa think

```python
def use_think_mode(case_use: CaseUse) -> bool:
    return case_use not in {
        CaseUse.SMOKE_TEST,
        CaseUse.HEALTH_LOOP_READ,
        CaseUse.HEALTH_LOOP_ANALYZE,     # ← desactivado
        CaseUse.SUMMARY,
        CaseUse.DAILY_SUMMARY,            # ← desactivado
        CaseUse.BACKUP,
        CaseUse.ALERT_REACTIVE,           # ← desactivado
        CaseUse.CHAT,
    }
```

Activado en: `GLOBAL_STATE`, `OPTIMIZATION`, `ONBOARDING`, `DIAGNOSE`, `CONVERSATION`, `THINK`.

## 🐛 El bug que nos hizo desactivarlo en mutaciones

> [!danger] Tool calls como texto
> Con `think=True`, observamos repetidamente que Qwen3 emite el tool call como **texto plano**:
> ```
> <tools>{"name":"restart_pod","arguments":{"namespace":"tenant-acme","pod_name":"x"}}</tools>
> ```
> En lugar de usar el mecanismo `tool_calls` del protocolo OpenAI. Pydantic-AI no detecta esto, y la tool NO se ejecuta.
>
> El resultado: el operador recibe un mensaje que **parece** decir "he reiniciado el pod" pero el reinicio no ocurrió.

## 🛡️ Mitigaciones

### 1. Desactivar think en modos que mutan

```python
CaseUse.HEALTH_LOOP_ANALYZE,    # mutaciones K8s
CaseUse.DAILY_SUMMARY,          # llama 10 tools
CaseUse.ALERT_REACTIVE,         # mutaciones K8s
```

### 2. Regla explícita en system prompt

> [!example] Texto añadido al prompt de modos que mutan
> ```text
> Prohibido escribir tool calls como texto (p.ej.
> <tools>{"name":"restart_deployment",...}</tools>).
> Tienen que ejecutarse como tool calls reales del modelo;
> en texto no surten efecto y el operador no podrá actuar.
> ```

### 3. Detección secundaria (deseable)

> [!warning] No implementado todavía
> Sería buena idea hacer post-procesado del texto de respuesta y, si detecta el patrón `<tools>...</tools>`, emitir un error o reintentar. Roadmap.

## ✅ Casos donde think SÍ brilla

- `THINK` Telegram (`/think <q>`): el operador quiere ver el razonamiento.
- `DIAGNOSE`: investiga incidencias usando reading tools (sin mutaciones).
- `CONVERSATION` (CLI/largo): preguntas profundas.
- `GLOBAL_STATE`: análisis sin mutar.
- `OPTIMIZATION`: razona qué hibernar (la mutación es decisión última, pero el modelo razona primero).

## 🧠 Salida con think

> [!example] Estructura de respuesta con think
> ```
> [Razonamiento interno - parsed como reasoning]
> El operador me pregunta X. Para responder bien necesito Y.
> Voy a consultar la tool Z.
> Tras ver el resultado, concluyo que...
>
> [Respuesta visible]
> La respuesta es ...
> ```
>
> Pydantic-AI parsea el razonamiento como parte del `result.all_messages()` pero la respuesta visible para el usuario es solo la parte final.

## 📈 Métrica `think` en `decisions_total`

```python
lobster_decisions_total = Counter(
    "lobster_decisions_total",
    "Agent decisions",
    ["case_use", "model", "think", "outcome"],
)
```

> [!tip] PromQL útil
> ```promql
> # Ratio think vs no-think
> sum by (think) (rate(lobster_decisions_total[1h]))
> ```

→ Continúa en [[04-Pydantic-AI]].

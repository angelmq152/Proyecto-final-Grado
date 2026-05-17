---
title: Limitaciones de los modelos LLM y mitigaciones
tags: [llm, limitaciones, mitigaciones, hallucinations]
---

# 🚧 Limitaciones LLM y mitigaciones

> [!abstract] Realismo
> Trabajar con LLMs sobre infra crítica obliga a aceptar que **el modelo se equivoca**. Esta nota lista las limitaciones observadas y cómo Lobster las mitiga.

## 1️⃣ Halucinación de nombres

> [!danger] El bug clásico
> El LLM inventa nombres de pods/deployments/namespaces, especialmente bajo presión (alerta reactiva).
>
> Ejemplos reales:
> - `nginx-7df4-default` cuando el pod real era `wordpress-abc123-xyz`.
> - `default` como namespace en un cluster sin `default` populated.

**Mitigaciones**:

1. **Prompt explícito**:
   ```text
   Usa SIEMPRE las herramientas para obtener datos reales antes de decidir nada.
   Nunca inventes nombres de pod, namespace o deployment.
   Nunca asumas que un recurso vive en el namespace 'default'.
   ```
2. **Confirmación con tools**: el flujo obligatorio en `alert_reactive` y `health_loop_analyze` exige llamar `list_pods` antes de actuar.
3. **Policy + RBAC**: si el LLM acaba pidiendo mutar un recurso inexistente, la llamada falla con `K8sClientError` y el agente lo reporta.

## 2️⃣ Tool calls como texto

> [!danger] Bug específico de Qwen3 con think
> Documentado en [[03-Think-mode#El bug]]. Emite `<tools>{...}</tools>` en lugar de tool_call real.

**Mitigaciones**:

1. **Desactivar think** en `HEALTH_LOOP_ANALYZE`, `DAILY_SUMMARY`, `ALERT_REACTIVE`.
2. **Prompt explícito** prohibiéndolo.
3. **(Futuro)** post-procesado para detectar el patrón y reintentar.

## 3️⃣ Latencia impredecible

> [!warning] El modelo a veces tarda 10x más que el promedio
> En `qwen3:32b` con prompt complejo, hemos visto runs de 8 min cuando el típico es 2 min. Razones: GPU saturada por otro proceso, modelo no caché, swap.

**Mitigaciones**:

1. **Timeouts agresivos** por modo (300s a 1800s).
2. **Cola FIFO** (Fase 9) para evitar competencia.
3. **OLLAMA_KEEP_ALIVE** alto para mantener modelo caliente entre runs.
4. **Métricas** alertan cuando p95 > 5 min.

## 4️⃣ Tokens consumidos en exceso

> [!info] El LLM a veces incluye dump de Prom en su respuesta
> Si una tool devuelve mucha data (300 series Prometheus), el LLM puede "transcribirla" en su respuesta consumiendo miles de tokens.

**Mitigaciones**:

1. **Truncado defensivo** en tools (`_truncate` a 500 chars).
2. **Modelos compactos** en `domain/models.py` y `tools/reading.py` (5-10 campos por entidad, no el objeto K8s completo).
3. **Métrica de tokens** `lobster_llm_tokens_total` permite detectar runs caros.

## 5️⃣ Inestabilidad en respuestas largas

> [!warning] qwen3:32b a veces se "atasca"
> Genera 90% del informe y luego empieza a repetirse infinitamente, agotando timeout.

**Mitigaciones**:

1. **timeout 1800s** para daily_summary (acota el daño).
2. **Prompt estructurado** con secciones explícitas → el modelo tiende a terminar cuando completa todas.
3. **Sin think** en daily_summary (think alarga el riesgo).

## 6️⃣ Falsos `[ANOMALÍA]`

> [!info] Histórico
> Las primeras versiones detectaban anomalía buscando keywords en el cuerpo (`"crashloopbackoff"`). Pero el LLM escribía *"no presentan errores como CrashLoopBackOff"* y disparaba un analyze caro.

**Mitigación**:

- Prefijo estructural: la respuesta debe empezar con `[OK]` o `[ANOMALÍA]`. Detección por `re.compile(r'\s*\[\s*anomal', re.IGNORECASE)` al inicio del string.

## 7️⃣ Pérdida de contexto largo

> [!warning] La memoria conversacional está acotada a 20 turnos
> Más allá, el agente "olvida" lo que se habló. En `/think` esto puede ser frustrante si el operador hace una serie larga.

**Mitigaciones**:

1. **`max_conversation_turns` configurable** (subir si memoria/coste lo permiten).
2. **SQLite guarda todo** — el operador puede consultar el histórico.
3. **`search_decisions`** tool permite recuperar contexto desde otras conversaciones del día.

## 8️⃣ Estilo inconsistente

> [!info] Markdown a veces mal formateado
> El LLM no siempre cierra los bloques de código, o mezcla `**bold**` y `__bold__`.

**Mitigación**:

- `md_to_mdv2()` en `telegram/formatting.py` hace conversión tolerante (cobertura `**`, `*`, `_`, code blocks).

## 9️⃣ Reproducibilidad

> [!warning] Mismo prompt, distinta respuesta
> Los LLMs no son deterministas (incluso con temperature=0 en local). Dos runs del mismo `daily_summary` producirán informes distintos.

**Aceptación**: es una característica del medio. Los tests verifican que la respuesta cumple ciertas propiedades estructurales (empieza con prefix, tiene secciones, llama tools), no el texto exacto.

## 🛡️ Recomendaciones generales

> [!tip] Filosofía
> 1. **Verificar todo**. Las tools de lectura son baratas; usarlas antes de mutar.
> 2. **Aprobaciones humanas** son la red de seguridad principal.
> 3. **Logs estructurados** en Loki para auditar cualquier decisión.
> 4. **Métricas conservadoras** que alerten ante anomalías.
> 5. **Modo paused** como kill switch instantáneo.

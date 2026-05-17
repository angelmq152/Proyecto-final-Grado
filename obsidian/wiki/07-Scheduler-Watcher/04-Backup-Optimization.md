---
title: Backup y Optimization (jobs nocturnos)
tags: [scheduler, backup, optimization, scale-to-zero]
---

# 🌙 Backup · Optimization

> [!abstract] Dos jobs nocturnos
> A las **2:00 AM** corre `backup` (razonamiento sobre estado backups) y a las **3:00 AM** corre `optimization` (decide candidatos a scale-to-zero).

## 💾 `backup` — 2:00 AM

```python
_BACKUP_PROMPT = (
    "Verifica el estado de los backups: comprueba qué tenants tienen backups "
    "pendientes según su tier (free=semanal, basic/premium=diario). "
    "Reporta el estado de cada tenant y cualquier backup fallido."
)
```

- Modelo: `qwen3:8b`, think ❌.
- Notify: ✅.
- Tools: meta + memory + k8s_basic (sin mutaciones).
- Timeout: 300 s.

> [!warning] No ejecuta backups
> El job **razona** sobre el estado pero no toca nada (no tiene mutation_tools). Asume que hay un script externo (Velero, restic, …) haciendo los backups reales.

## ⚡ `optimization` — 3:00 AM

```python
_OPTIMIZATION_PROMPT = (
    "Identifica tenants del tier 'free' sin actividad reciente (sin requests "
    "en Ingress en las últimas 2 horas). Para cada candidato a scale-to-zero, "
    "comprueba el historial de decisiones: si ya fue aprobado antes, ejecuta "
    "el scale-to-zero de forma autónoma. Si es la primera vez, solicita aprobación."
)
```

- Modelo: `qwen3:8b`, think ✅.
- Notify: ❌ (silencioso salvo que haya aprobaciones).
- Tools: meta + prometheus + k8s_basic + memory + mutations.
- Timeout: 600 s.

## 🧠 Lógica del scale-to-zero condicional

> [!example] Cómo razona el agente
> 1. Lista todos los namespaces tenant con `list_namespaces`.
> 2. Filtra los con `saasphere.io/tier=free`.
> 3. Para cada uno, `query_prometheus_instant` sobre `rate(traefik_router_requests_total[2h])`.
> 4. Si ratio = 0 → candidato.
> 5. Para cada candidato, `search_decisions(case_use="optimization", limit=20)` y busca si ya hubo aprobación previa para ese namespace.
> 6. **Sí hubo** → llama `scale_deployment(ns, deploy, 0)` directo. Severidad NORMAL (no CRITICAL por `prior_scale_to_zero=true`).
> 7. **No hubo** → llama `scale_deployment(ns, deploy, 0)` y se pide aprobación CRITICAL al humano.

> [!tip] El "recuerdo" es persistente
> La detección de `prior_scale_to_zero` la hace `_has_prior_scale_to_zero` en `tools/mutations/k8s.py` consultando el ledger `actions`. **No depende del razonamiento LLM**, es código determinista.

## 🚏 Severidad dinámica del scale a 0

```python
def _scale_deployment_severity(context):
    replicas = context.get("replicas", context.get("target_replicas"))
    if replicas == 0 and not bool(context.get("prior_scale_to_zero")):
        return ActionSeverity.CRITICAL
    return ActionSeverity.NORMAL
```

→ Defined en `domain/policy.py`. Usada también desde `scale_deployment` directamente.

## 🔁 Resucitar tenants

> [!info] Cuando alguien visita
> No hay un "wake on request" implementado. Si un tenant está scaled-to-zero y alguien intenta acceder a su Ingress, **Traefik devuelve 404** porque no hay backend. El operador (o un script externo) tiene que ejecutar `pause_tenant` / `resume_tenant` o `scale_deployment` para devolverlo.
>
> Roadmap: `wake_on_request` (KEDA o un middleware Traefik custom).

→ Ver [[../12-Decisiones-Limitaciones/05-Futuro-roadmap#Wake-on-request]].

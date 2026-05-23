---
title: 03 · Tools — MOC
tags: [moc, tools, lobster, pydantic-ai]
---

# 🛠️ 03 · Tools — MOC

> [!abstract] El "API" del agente hacia el mundo
> Lobster no tiene acceso libre a nada: solo puede invocar **funciones registradas**. Cada función está tipada con Pydantic, tiene docstring que el LLM lee, y devuelve datos compactos para ahorrar tokens. Hay dos familias: **lectura** (no muta nada) y **mutación** (puede cambiar el estado del clúster, pasa por `MutationContext`).

## Notas — Lectura

> Las tools de lectura están en `lobster_agent/agent/tools/reading.py`.

- [[01-Reading-Prometheus]] — `query_prometheus_instant`, `query_prometheus_range`, `get_node_health`.
- [[02-Reading-Loki]] — `query_loki_logs`, `get_recent_errors`.
- [[03-Reading-K8s]] — `list_pods`, `get_pod`, `list_deployments`, `list_ingresses`, `list_namespaces`, `list_recent_events`.
- [[04-Reading-Alertmanager]] — `list_active_alerts`, `get_alert_details`.
- [[05-Reading-Memory]] — `search_decisions`, `get_decision`.

## Notas — Mutación

> Las tools de mutación están en `lobster_agent/agent/tools/mutations/`.

- [[06-Mutations-K8s]] — `restart_pod`, `restart_deployment`, `scale_deployment`, `delete_pod_persistent`, `apply_manifest`, `update_configmap`.
- [[07-Mutations-Tenants]] — `deploy_tenant`, `delete_tenant`, `pause_tenant`, `resume_tenant`, `verify_tenant_health`.
- [[08-Mutations-Nodes]] — `pin_deployment_to_node`, `unpin_deployment_from_node`, `cordon_node`, `uncordon_node`. También documenta `is_node_alive` con probe TCP y campo `api_available`.

## Notas — Meta y debug

- [[09-Meta-request-new-tool]] — el agente puede pedir nuevas herramientas.
- [[10-Dummy-tools]] — `get_time`, `echo`, `simple_calc` para smoke tests.

## Tabla rápida: severidad por tool

| Tool | Severidad | Aprobación |
|---|---|---|
| `restart_pod` (en CrashLoopBackOff) | AUTONOMOUS | ❌ |
| `restart_pod` (otro estado) | NORMAL | ✅ |
| `restart_deployment` | NORMAL | ✅ |
| `scale_deployment` (→ N>0) | NORMAL | ✅ |
| `scale_deployment` (→ 0 primera vez) | CRITICAL | ✅ |
| `delete_pod_persistent` | NORMAL | ✅ |
| `apply_manifest` | NORMAL | ✅ |
| `update_configmap` | NORMAL | ✅ |
| `deploy_tenant` | CRITICAL | ✅ |
| `delete_tenant` | CRITICAL | ✅ (+ confirm namespace) |
| `pause_tenant` | NORMAL | ✅ |
| `resume_tenant` | AUTONOMOUS | ❌ |
| `verify_tenant_health` | AUTONOMOUS | ❌ |
| `pin_deployment_to_node` | AUTONOMOUS | ❌ (desde 2026-05-23) |
| `unpin_deployment_from_node` | AUTONOMOUS | ❌ |
| `cordon_node` | NORMAL | ✅ |
| `uncordon_node` | AUTONOMOUS | ❌ |

→ Ver [[../02-Agente/05-Mutation-context|MutationContext]] para entender cómo se aplica esto.

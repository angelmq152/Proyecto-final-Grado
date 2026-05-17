---
title: Mutations — Nodes (pin/unpin)
tags: [tools, mutations, nodes, pin, unpin, fase8]
---

# 📌 Mutations · Nodos (pin/unpin)

> [!abstract] Migración entre matrix y fallback
> Archivo: `lobster_agent/agent/tools/mutations/node.py`. **Fase 8** añadió esta capacidad: cuando matrix está saturado, mover workloads concretos a fallback; cuando matrix se recupera, soltarlos para que K8s vuelva a programar normal.

## 🎯 `pin_deployment_to_node(namespace, deployment_name, node)`

> [!warning] Severidad NORMAL — requiere aprobación
> `node` está restringido a `Literal["matrix", "fallback"]` para evitar pinar a hosts que no son nodos K3s (leia, sauron, heimdall).

> [!info] Auto-tolerations
> El nodo fallback lleva el taint `saasphere/role=fallback:NoSchedule`. Sin tolerations el pod no se planificaría aunque pongamos nodeSelector. La tool:
>
> 1. Lee `nodeSelector` actual del Deployment (`get_deployment_node_selector`).
> 2. Lee `tolerations` actuales (`get_deployment_tolerations`).
> 3. Lee taints del nodo destino (`get_node_taints`).
> 4. Genera tolerations matching para cada taint:
>    ```python
>    {"key": "saasphere/role", "operator": "Equal", "value": "fallback", "effect": "NoSchedule"}
>    ```
> 5. Hace `patch_deployment_placement(ns, name, nodeSelector, tolerations)` — un solo patch.

> [!example] Resultado en K8s
> ```yaml
> spec:
>   template:
>     spec:
>       nodeSelector:
>         kubernetes.io/hostname: fallback
>       tolerations:
>         - key: saasphere/role
>           operator: Equal
>           value: fallback
>           effect: NoSchedule
> ```

## 🆓 `unpin_deployment_from_node(namespace, deployment_name)`

> [!info] AUTONOMOUS — no necesita aprobación
> Quita el `nodeSelector` (lo pone a `None`) y elimina **solo** las tolerations con prefijo `saasphere/` (las añadidas por `pin`). Las tolerations originales del deployment se preservan.

> [!tip] Por qué es autónoma
> "Unpin" es relajar una restricción, no imponer una nueva. K8s recolocará el pod donde quiera (probablemente vuelva a matrix). El operador no necesita aprobar cada vez que matrix se recupera.

## 🧠 Política de uso desde `health_loop`

El prompt de `HEALTH_LOOP_READ` incluye:

```text
(C) Workloads pinados pendientes de devolver: lista deployments en
namespaces de tenant. Si alguno tiene nodeSelector kubernetes.io/hostname=fallback
Y matrix está Ready con CPU < {unpin_cpu_pct}% y memoria < {unpin_mem_pct}%,
marca con '[ANOMALÍA]' y empieza la descripción con 'workloads pinados a
fallback con matrix recuperado'.
```

Y el de `HEALTH_LOOP_ANALYZE`:

```text
Si la anomalía es 'workloads pinados a fallback con matrix recuperado':
(1) confirma con query_prometheus_range que matrix ha estado por debajo
del umbral UNPIN durante los últimos 15 minutos.
(2) list_deployments y filtra los que tienen nodeSelector kubernetes.io/hostname=fallback.
(3) unpin_deployment_from_node(namespace, deployment) para cada uno.
Autónomo, sin aprobación.
```

> [!tip] Umbrales por defecto
> En `SchedulerConfig`:
> - `node_pressure_cpu_threshold_pct = 85.0` → matrix bajo presión.
> - `node_pressure_memory_threshold_pct = 85.0`
> - `node_pressure_unpin_cpu_threshold_pct = 70.0` → matrix recuperado.
> - `node_pressure_unpin_memory_threshold_pct = 70.0`
> - `node_pressure_unpin_stable_minutes = 15` → durante este tiempo bajo umbral.

## 🛡️ Reglas de seguridad

> [!danger] Si fallback también está saturado: NO actuar
> El system prompt de health_loop_analyze incluye:
> *"Si fallback tambien esta bajo presion (segun get_node_health), notifica al operador y NO actues. Es la regla de seguridad mas importante."*
>
> Pinar a un nodo ya saturado solo movería el problema.

→ Documento académico de la fase en `obsidian/TFG_Fase8_Lobster.md`.

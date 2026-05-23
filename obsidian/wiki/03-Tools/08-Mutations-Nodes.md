---
title: Mutations — Nodes (pin/unpin)
tags: [tools, mutations, nodes, pin, unpin, fase8]
---

# 📌 Mutations · Nodos (pin/unpin)

> [!abstract] Migración entre matrix y fallback
> Archivo: `lobster_agent/agent/tools/mutations/node.py`. **Fase 8** añadió esta capacidad: cuando matrix está saturado o caído, mover workloads concretos a fallback sin esperar aprobación humana; cuando matrix se recupera, soltarlos para que K8s vuelva a programar normal. Desde la sesión del 2026-05-23, `pin_deployment_to_node` es **AUTÓNOMO** (igual que `unpin`).

## 🎯 `pin_deployment_to_node(namespace, deployment_name, node)`

> [!tip] Severidad AUTONOMOUS desde 2026-05-23 — no requiere aprobacion
> Antes de esta fecha tenía severidad `NORMAL` (requería aprobación Telegram). El cambio se hizo en `lobster_agent/domain/policy.py` al validar el primer failover real: ante la caída de un nodo, la urgencia de migrar pods no es compatible con esperar confirmación humana. `node` está restringido a `Literal["leia", "matrix", "fallback"]` para evitar pinar a hosts externos (sauron, heimdall).

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

> [!tip] Ejecucion en el ciclo de recuperacion (validado 2026-05-23)
> `unpin_deployment_from_node` no es solo una tool para uso manual por Telegram. En el ciclo de recuperación autónoma validado el 23 de mayo de 2026, Lobster la llamó tres veces seguidas de forma autónoma al detectar que matrix había vuelto y los workloads seguían pinados a fallback. El detonante fue la instrucción en `HEALTH_LOOP_READ` de llamar `list_deployments` en cada ciclo y reportar los deployments con `node_selector={"kubernetes.io/hostname":"fallback"}` como anomalía cuando matrix está `alive=True`.

> [!example] Comando para la captura
> ```bash
> # Ver las acciones de unpin en el ledger
> sqlite3 /var/lib/lobster/state.db \
>   "SELECT status, severity, action_type, namespace || '/' || target_name, created_at \
>    FROM actions \
>    WHERE action_type = 'unpin_deployment_from_node' \
>    ORDER BY created_at DESC LIMIT 5;"
> ```

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

## 🔍 `is_node_alive(node)` — lectura con probe TCP de fallback

Herramienta de lectura definida en `lobster_agent/agent/tools/reading.py`. A partir de la sesión 2026-05-23, el modelo de retorno `NodeAliveness` incluye el campo `api_available`.

### Modelo de retorno

```python
class NodeAliveness(BaseModel):
    node: Literal["matrix", "fallback"]
    alive: bool
    api_available: bool
    detail: str
```

### Tres estados posibles

| `alive` | `api_available` | Descripcion operativa |
|---|---|---|
| `True` | `True` | Estado normal: nodo Ready según la API K8s |
| `True` | `False` | Nodo alcanzable por TCP (puerto 22), pero la API K8s no responde — no actuar sobre scheduling |
| `False` | `False` | Nodo apagado o sin red: tanto la API como el probe TCP fallaron |

Nota importante: cuando matrix cae como worker, la API K8s (que corre en leia) sigue respondiendo. Por tanto `is_node_alive('matrix')` cuando matrix está apagado devuelve `alive=False, api_available=True` — no `api_available=False`.

### Flujo interno

```
is_node_alive(node)
  │
  ├─ k8s.get_node_ready(node) ──► OK ──► NodeAliveness(alive=Ready, api_available=True)
  │
  └─ K8sClientError
        │
        ├─ _probe_node_tcp(node, port=22, timeout=3.0)
        │       │
        │       ├─ TCP OK ──► NodeAliveness(alive=True, api_available=False)
        │       │
        │       └─ TCP falla ──► NodeAliveness(alive=False, api_available=False)
```

> [!tip] Por que importa api_available para el TFG
> El campo `api_available` añade **observabilidad de segundo nivel**: cuando el canal primario (API K8s) falla, hay un canal secundario (TCP probe a puerto 22). Esto implementa el patrón "health check with degraded mode" — el agente puede reportar el estado del nodo incluso cuando la infraestructura de gestión está degradada, sin confundir "API no disponible" con "nodo apagado".

> [!example] Comando para la captura
> ```bash
> # Ver el código de _probe_node_tcp en reading.py
> grep -n -A 10 "_probe_node_tcp" \
>   /opt/openclaw/lobster_agent/agent/tools/reading.py
>
> # Simular los tres casos manualmente via kubectl
> # Caso alive=True, api_available=True (estado normal):
> kubectl --kubeconfig=/etc/lobster/kubeconfig \
>   get node matrix -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
>
> # Caso alive=False, api_available=True (matrix apagado):
> # → la query de arriba devuelve "False" y la API responde bien
> ```

## 🧱 `cordon_node` y `uncordon_node`

Herramientas añadidas junto con pin/unpin. Marcan un nodo como no-schedulable (`kubectl cordon`) o lo reintegran (`kubectl uncordon`).

| Tool | Severidad | Uso típico |
|---|---|---|
| `cordon_node` | NORMAL (requiere aprobación) | Evacuar un nodo antes de mantenimiento |
| `uncordon_node` | AUTONOMOUS | Reintegrar un nodo tras mantenimiento |

El flujo habitual de evacuación manual es: `cordon_node` → `restart_deployment` para cada tenant → el nodo recuperado → `uncordon_node`.

> [!example] Comando para la captura
> ```bash
> # Estado de scheduling de los nodos
> kubectl --kubeconfig=/etc/lobster/kubeconfig get nodes \
>   -o custom-columns="NAME:.metadata.name,SCHEDULABLE:.spec.unschedulable,STATUS:.status.conditions[-1].type"
> ```

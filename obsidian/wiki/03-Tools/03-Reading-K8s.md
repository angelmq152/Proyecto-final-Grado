---
title: Reading — K8s tools
tags: [tools, reading, k8s, kubernetes, lightkube]
---

# ☸️ Reading · Kubernetes

> [!abstract] El agente ve el clúster
> Seis tools de lectura que devuelven datos compactos y tipados. Todas usan `K8sClient` (lightkube AsyncClient) por debajo. Llamarlas **sin namespace** itera por todos los namespaces visibles.

## 🛠️ `list_pods(namespace=None)`

> [!example] Salida
> ```text
> [
>   PodSummary(name="wordpress-7b6f", namespace="tenant-acme", phase="Running",
>              restarts=0, age_minutes=420, container_statuses_brief="wordpress:ready=True,restarts=0")
> ]
> ```
> Si `namespace=None`, lista *todos* los namespaces.

## 🛠️ `get_pod(namespace, name)`

> [!example] Detalle completo
> Devuelve `PodDetail(... ready, node)` además de los campos de `PodSummary`. Se usa antes de mutar para confirmar estado real.

## 🛠️ `list_deployments(namespace=None)`

> [!example] Salida
> `DeploymentSummary(name, namespace, replicas, ready_replicas, available_replicas, node_selector)`. Se usa típicamente para detectar `replicas != ready_replicas` y para comprobar si hay deployments pinados a un nodo concreto.

> [!tip] Campo `node_selector` (añadido 2026-05-23)
> Desde la sesión del 23 de mayo de 2026, `DeploymentSummary` incluye el campo `node_selector: dict[str, str] | None`. Cuando un deployment tiene `nodeSelector` en K8s (por ejemplo `{"kubernetes.io/hostname": "fallback"}` tras un pin de failover), este valor llega al LLM como parte de la respuesta. Antes de este cambio, el agente no podía detectar los pins y por tanto no podía ejecutar el ciclo de recuperación autónoma.
>
> La cadena de propagación es:
> `K8s API → lightkube Deployment → _deployment_info_from_deployment() → DeploymentInfo.node_selector → _deployment_summary() → DeploymentSummary.node_selector → LLM`

> [!warning] Leccion de implementacion: `_get_attr` no encadena
> Durante la implementación se descubrió un bug sutil: para acceder a `deployment.spec.template.spec.nodeSelector` son necesarias tres llamadas independientes a `_get_attr`, no una sola con múltiples argumentos. `_get_attr(spec, "template", "spec")` busca `spec.template` **o** `spec.spec` (alternativas), no encadena. La forma correcta:
> ```python
> template = _get_attr(spec, "template")
> pod_spec = _get_attr(template, "spec")
> raw_selector = _get_attr(pod_spec, "nodeSelector", "node_selector")
> ```
> Ver [[../10-Operacion/09-Postmortem-Failover-Kubeconfig-2026-05-23]] (Bug 2) para el análisis completo.

> [!example] Comando para la captura
> ```bash
> # Ver node_selector de todos los deployments de tenant
> kubectl --kubeconfig=/etc/lobster/kubeconfig get deployments \
>   -A -l saasphere.io/tenant=true \
>   -o custom-columns="NAMESPACE:.metadata.namespace,NAME:.metadata.name,NODE:.spec.template.spec.nodeSelector"
>
> # Ver el modelo DeploymentSummary en el codigo
> grep -n -A 10 "class DeploymentSummary" \
>   /opt/openclaw/lobster_agent/agent/tools/reading.py
> ```

## 🛠️ `list_ingresses(namespace=None)`

> [!example] Salida
> `IngressSummary(name, namespace, hosts, tls, address, age_minutes)`. `address` viene de `status.loadBalancer.ingress[].ip|hostname`. Útil para verificar que un tenant está expuesto.

## 🛠️ `list_recent_events(namespace=None, minutes=30)`

> [!example] Salida
> `K8sEvent(type, reason, object, message, age_minutes)`. Filtra eventos por antigüedad. Es esencial para diagnosticar por qué un pod no arranca.

## 🛠️ `list_namespaces()`

> [!example] Salida
> Lista de `NamespaceInfo(name)`. Sin filtro. Útil para iterar.

## 🧬 Modelos compactos

```python
class PodSummary(BaseModel):
    name: str
    namespace: str
    phase: str | None
    restarts: int
    age_minutes: int | None
    container_statuses_brief: str

class PodDetail(PodSummary):
    ready: bool
    node: str | None

class DeploymentSummary(BaseModel):
    name: str
    namespace: str
    replicas: int | None
    ready_replicas: int | None
    available_replicas: int | None
    node_selector: dict[str, str] | None = None  # añadido 2026-05-23
```

> [!info] Compacto a propósito
> Los modelos K8s nativos son **enormes** (cientos de campos). Compactarlos a 5-10 campos ahorra ~80 % de tokens al LLM por respuesta.

## 🔌 Bajo el capó: `K8sClient`

```python
class K8sClient:
    def __init__(self, kubeconfig_path, timeout_seconds=10.0):
        ...
    async def list_pods(self, namespace) -> list[Pod]: ...
    async def get_pod(self, namespace, name) -> Pod: ...
    async def list_deployments(...) -> list[Deployment]: ...
    async def list_ingresses(...) -> list[dict]: ...      # devuelve dict resumen
    async def list_events(...) -> list[Event]: ...
    async def list_namespaces(label_selector=None) -> list[Namespace]: ...
```

> [!warning] `K8sClientError` envuelve toda excepción
> El cliente captura cualquier `Exception` de lightkube y la re-lanza como `K8sClientError`. Las tools la convierten a `ToolError(source="k8s", ...)`.

## 🚫 Recursos NO listables

> [!danger] Lo que el agente NO puede leer
> - Secrets (bloqueados por el RBAC del kubeconfig)
> - ServiceAccounts
> - Roles / RoleBindings
> - Resources de cluster-scope que no sean Namespaces ni Nodes
>
> Esto es **deliberado**: principio de privilegio mínimo. Si el agente necesita ver un Secret, debe pedir aprobación humana fuera de banda.

## 🔁 Iteración cross-namespace

> [!example] Cuando `namespace=None`
> ```python
> namespaces = await list_namespaces(ctx)
> for ns in namespaces:
>     pods.extend(await k8s.list_pods(ns.name))
> ```
> Esto es **caro** en clústeres grandes pero perfectamente viable en SaaSphere (decenas de namespaces como mucho).

→ Mutaciones de pods/deployments en [[06-Mutations-K8s]].

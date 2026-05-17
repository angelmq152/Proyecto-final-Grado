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
> `DeploymentSummary(name, namespace, replicas, ready_replicas, available_replicas)`. Se usa típicamente para detectar `replicas != ready_replicas`.

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

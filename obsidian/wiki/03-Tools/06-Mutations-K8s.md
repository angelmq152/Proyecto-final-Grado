---
title: Mutations — K8s básicas
tags: [tools, mutations, k8s, restart, scale, configmap]
---

# 🔧 Mutations · K8s básicas

> [!abstract] Las 6 mutaciones primarias
> Archivo: `lobster_agent/agent/tools/mutations/k8s.py`. Todas pasan por `MutationContext` antes de tocar K8s.

## 🔁 `restart_pod(namespace, pod_name)`

> [!info] Severidad dinámica
> Si el pod **está en CrashLoopBackOff** *y* el namespace es tenant (`saasphere.io/tenant=true`), severidad → `AUTONOMOUS`. En cualquier otro caso → `NORMAL` (aprobación).

> [!example] Mecanismo
> No usa `kubectl rollout restart`. Hace **`DELETE` del pod** y deja que el ReplicaSet/Deployment lo recree. Comprueba `owner_references` y avisa si el pod es standalone (sin owner) → no se recreará.

> [!danger] El docstring está sobreentrenado
> La docstring incluye varias frases para forzar al LLM a llamar la tool en lugar de explicar con texto:
> *"Call this tool whenever the user asks to restart, reboot, or fix a pod. … Do NOT respond with a text explanation instead of calling this tool when the user requests a pod restart."*

## 🔁 `restart_deployment(namespace, deployment_name)`

> [!info] Rolling restart
> Patchea `spec.template.metadata.annotations["kubectl.kubernetes.io/restartedAt"] = now.isoformat()` igual que hace `kubectl rollout restart`. Severidad: `NORMAL` siempre.

## 📏 `scale_deployment(namespace, deployment_name, replicas)`

> [!info] Severidad condicionada
> ```python
> severity = (
>     ActionSeverity.CRITICAL
>     if replicas == 0 and not prior_scale_to_zero
>     else ActionSeverity.NORMAL
> )
> ```
> `prior_scale_to_zero` se calcula consultando el ledger `actions` (busca scale_deployment previos con `replicas=0` para el mismo target).
>
> La primera vez que escalas a cero un deployment **es crítico** (puedes dejar al tenant caído). La segunda vez ya no.

> [!warning] No se permiten `replicas < 0`
> Validación temprana antes de llegar al MutationContext.

## 🗑️ `delete_pod_persistent(namespace, pod_name)`

> [!info] El que NO recrea
> Si el pod tiene `owner_references`, Kubernetes lo recreará y la tool advierte: *"Warning: pod has an owner and will be recreated by Kubernetes."*
>
> Útil para pods standalone "anyway". Severidad: `NORMAL`.

## 📄 `apply_manifest(yaml_text)`

> [!info] Aplica un único recurso
> Parseo: un solo documento YAML. Validaciones:
> - `kind` requerido y dentro de allowlist (`Deployment, Service, ConfigMap, Ingress, PVC, Namespace, HPA, Secret, ResourceQuota`).
> - Política bloquea `Secret, ServiceAccount, Role*, ClusterRole*, Pod`.
> - Si `metadata.namespace` existe el cliente hace upsert (get → si existe replace, si no create).
>
> Severidad: `NORMAL` siempre.

> [!danger] No es multi-doc
> Si pasas YAML con `---` separadores, la tool rechaza el manifest. Para multi-doc se usa `deploy_tenant` que renderiza Jinja2 y aplica los recursos en orden de dependencia.

## 🔁 `update_configmap(namespace, name, data)`

> [!info] Merge, no replace
> Patchea solo las claves indicadas. Las existentes no listadas se preservan. Severidad: `NORMAL`.

## 🧬 Helpers compartidos

> [!tip] Lectura previa a la mutación
> Cada tool **primero lee** antes de mutar:
> - `get_pod` para confirmar estado.
> - `get_namespace` para leer labels (`saasphere.io/tenant`).
> - `get_deployment` para replicas actuales.
>
> Esto evita pedir aprobación para una mutación sobre un recurso inexistente.

> [!warning] Si la lectura previa falla
> Devuelve string `"<tool> failed before action creation: <error>"`. **No se crea Action en SQLite** porque no se ha pasado por `MutationContext.execute`. Esto deja la base limpia de "intentos abortados".

## 🧪 Tests

- `tests/test_k8s_mutations.py` — todas las tools con K8sClient mockeado.
- `tests/test_restart_pod.py` — caso especial de CrashLoopBackOff y severidad autónoma.
- `tests/test_mutation_context.py` — verifica la máquina de estados.

→ Sigue en [[07-Mutations-Tenants]].

---
title: SaaSphere — Cluster K3s
tags: [infraestructura, saasphere, k3s, cluster]
---

# ☸️ SaaSphere · Cluster K3s

> [!abstract] El clúster que Lobster orquesta
> SaaSphere es un clúster **K3s** (distro K8s liviana) corriendo sobre dos nodos: `matrix` (control-plane + workloads) y `fallback` (cold standby tainted). Es lo único que Lobster puede mutar.

## 🧱 Composición

| Pieza | Estado |
|---|---|
| **K3s server** | `matrix` (control plane) |
| **K3s agent / worker** | `fallback` (cold standby) |
| **Etcd** | embedded en K3s (sqlite por defecto) |
| **CNI** | flannel (default K3s) |
| **Ingress** | Traefik (built-in K3s) |
| **DNS** | CoreDNS (built-in K3s) |
| **Metrics server** | metrics-server (built-in K3s) |
| **Almacenamiento** | local-path provisioner (built-in K3s) |
| **Cert-manager** | desplegado aparte para Let's Encrypt |

## 🏠 Namespaces

| Namespace | Bloqueado por policy | Propósito |
|---|---|---|
| `kube-system` | ✅ | sistema K3s |
| `kube-public` | ✅ | ConfigMap público |
| `metallb-system` | ✅ | LoadBalancer (si está) |
| `saasphere-system` | ✅ | servicios SaaSphere internos |
| `tenant-*` | ❌ (mutable si label `saasphere.io/tenant=true`) | clientes |

→ Detalle de política en [[../09-Tenants/06-Politica-namespaces]].

## 🔐 Acceso

> [!info] Un kubeconfig dedicado
> Lobster usa `/etc/lobster/kubeconfig` que apunta al control plane (`matrix:6443`) con credenciales basadas en un ServiceAccount con RBAC limitado. No usa el kubeconfig admin de K3s.

→ Ver [[05-RBAC-Kubeconfig]].

## 📦 Tipos de recurso que Lobster lee/modifica

> [!example] `K8sClient` registra estas resources de lightkube:
> - `Namespace` (read + delete)
> - `Pod` (read + delete)
> - `Deployment` + `DeploymentScale` (read + patch)
> - `ConfigMap` (read + patch)
> - `Service` (read)
> - `Ingress` (read)
> - `PersistentVolumeClaim` + `PersistentVolume` (read)
> - `ResourceQuota` (read)
> - `Event` (read + watch)
> - `Node` (read taints)
> - `Secret` (solo create vía apply_manifest, restringido a tenants)
> - `HorizontalPodAutoscaler` (read + apply)

## 🚦 Recursos protegidos

> [!danger] Nunca tocar
> `policy.py:PROTECTED_RESOURCE_NAMES = ("traefik", "coredns", "metrics-server")`. Cualquier mutación que toque algo cuyo nombre contenga estas substrings se bloquea con `aborted_policy`.

## 🌐 DNS

> [!info] `*.saasphere.local` y dominios reales
> - Los tenants en plantilla pueden tener hostname `tenant-name.saasphere.local` (interno) o un dominio real (con cert-manager + Let's Encrypt).
> - El template detecta:
>   ```jinja
>   {% if not hostname.endswith('.saasphere.local') %}
>     cert-manager.io/cluster-issuer: letsencrypt-prod
>     traefik...router.entrypoints: websecure
>   {% else %}
>     traefik...router.entrypoints: web
>   {% endif %}
>   ```

→ Continúa en [[02-Nodos-matrix-fallback]] y [[03-Hosts-LeIA-Sauron-Heimdall]].

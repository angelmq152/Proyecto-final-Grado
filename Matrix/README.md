# Matrix

Nodo de **orquestación de contenedores** del homelab SaaSphere.

## Servicios

- **K3s** ([`opt/k3s/`](./opt/k3s)) — Distribución ligera de Kubernetes. Aloja los namespaces `tenant-<nombre>` que el agente Lobster gestiona desde LeIA.
  - `leia-rbac.yaml` — Role + RoleBinding que da al agente Lobster los permisos mínimos sobre los namespaces de tenants.
- **Registry Docker** ([`opt/registry/`](./opt/registry)) — Registro privado de imágenes para el cluster.
  - `docker-compose.yml` — Definición del servicio (puerto, volumen, auth).

## Filesystem espejado

- `opt/k3s/` — Manifests aplicados al cluster (no es el state de K3s, solo declaraciones).
- `opt/registry/` — Stack docker-compose del registry.

## Notas

Solo se permiten mutaciones en namespaces con label `saasphere.io/tenant=true` (regla en `LeIA/opt/lobster/lobster_agent/domain/policy.py`). Los namespaces de sistema (`kube-system`, etc.) están hard-blocked.

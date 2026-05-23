---
title: 09 · Tenants — MOC
tags: [moc, tenants, saasphere, multitenant]
---

# 🏢 09 · Tenants — MOC

> [!abstract] Multi-tenancy en SaaSphere
> Cada cliente vive en su propio namespace marcado con `saasphere.io/tenant=true`. Lobster solo puede mutar dentro de namespaces que llevan esa etiqueta — todo lo demás está bloqueado por policy. Hay 3 **tiers** (free / basic / premium) que fijan límites de CPU/RAM/PVC y 3 **tipos** de tenant (wordpress / static_site / web_app) con plantilla Jinja2 propia.

## Notas

- [[01-Modelo-multi-tenant]] — namespaces, labels, política.
- [[02-Tiers]] — FREE/BASIC/PREMIUM y sus cuotas.
- [[03-Tipos]] — WordPress, Static, Web App.
- [[04-Plantillas-Jinja2]] — dentro de `lobster_agent/manifests/`.
- [[05-Ciclo-de-vida]] — deploy → pause → resume → delete.
- [[06-Politica-namespaces]] — qué NO puede tocar el agente.
- [[07-Postmortem-Static-Site-SMB]] — saga completa de la migración a `StorageClass` con `subDir` plantillado (2026-05-22/23).

## Tabla resumen de tiers

| Tier | CPU req/limit | RAM req/limit | Replicas | Storage |
|---|---|---|---|---|
| **FREE** | 50m / 200m | 64Mi / 256Mi | 1 | 1Gi |
| **BASIC** | 100m / 500m | 128Mi / 512Mi | 1 | 5Gi |
| **PREMIUM** | 250m / 1000m | 256Mi / 1Gi | 2 | 10Gi |

> [!tip] Conversión automática en WordPress
> Como WordPress = WP + MariaDB en el mismo namespace, Lobster duplica las cuotas (`_double_quantity()` en `manifests.py`) para que el ResourceQuota cubra ambos pods.

---
title: Tiers — FREE, BASIC, PREMIUM
tags: [tenants, tiers, cuotas, recursos]
---

# 🪜 Tiers · FREE · BASIC · PREMIUM

> [!abstract] Tres niveles, tres cuotas
> Archivo: `lobster_agent/domain/tenants.py`. Cada tier define límites de CPU, RAM, replicas y almacenamiento. Las cuotas se materializan en `ResourceQuota` por namespace cuando `deploy_tenant` aplica la plantilla.

## 📊 Tabla de tiers

| Tier | CPU req | CPU limit | RAM req | RAM limit | Replicas | Storage |
|---|---|---|---|---|---|---|
| **FREE** | 50m | 200m | 64Mi | 256Mi | 1 | 1Gi |
| **BASIC** | 100m | 500m | 128Mi | 512Mi | 1 | 5Gi |
| **PREMIUM** | 250m | 1000m | 256Mi | 1Gi | 2 | 10Gi |

## 🧬 Definición en código

```python
class TenantTier(StrEnum):
    FREE = "free"
    BASIC = "basic"
    PREMIUM = "premium"

@dataclass(frozen=True)
class TierLimits:
    cpu_request: str
    cpu_limit: str
    memory_request: str
    memory_limit: str
    replicas: int
    storage: str

TIER_LIMITS: dict[TenantTier, TierLimits] = {
    TenantTier.FREE: TierLimits("50m", "200m", "64Mi", "256Mi", 1, "1Gi"),
    TenantTier.BASIC: TierLimits("100m", "500m", "128Mi", "512Mi", 1, "5Gi"),
    TenantTier.PREMIUM: TierLimits("250m", "1000m", "256Mi", "1Gi", 2, "10Gi"),
}
```

## 🎛️ Cómo se materializan

Cuando `deploy_tenant` aplica la plantilla, los `{{ limits.cpu_request }}` etc. se sustituyen con los valores del tier. El resultado:

```yaml
# Deployment de tenant-acme FREE:
resources:
  requests:
    cpu: "50m"
    memory: "64Mi"
  limits:
    cpu: "200m"
    memory: "256Mi"
```

Y el `ResourceQuota`:

```yaml
spec:
  hard:
    requests.cpu: "50m"
    limits.cpu: "200m"
    requests.memory: "64Mi"
    limits.memory: "256Mi"
    persistentvolumeclaims: "1"
    requests.storage: "1Gi"
```

## 🍷 Duplicado para WordPress

> [!warning] WordPress son DOS pods
> WordPress + MariaDB en el mismo namespace. La cuota debe cubrir ambos. `manifests.py:_double_quantity` duplica las cantidades automáticamente:
> ```python
> def _double_quantity(value: str) -> str:
>     for suffix in ("Mi", "Gi", "m"):
>         if value.endswith(suffix):
>             return f"{int(value[:-len(suffix)]) * 2}{suffix}"
>     if value.isdigit():
>         return str(int(value) * 2)
>     return value
> ```
> Esto sucede en `ManifestRenderer.render` cuando el tipo es WORDPRESS, sustituyendo `quota_limits.*` en lugar de `limits.*`.

## 🤖 Acciones automáticas por tier

> [!example] Backup
> El prompt de `backup` indica:
> *"free=semanal, basic/premium=diario"*
> El job razona qué tenants necesitan backup hoy.

> [!example] Optimization (scale-to-zero)
> El prompt de `optimization` solo apunta a tier free:
> *"Identifica tenants del tier 'free' sin actividad reciente..."*
> Los basic/premium nunca se hibernan automáticamente.

## 🧪 Cambiar de tier

> [!warning] No hay tool para cambiar de tier
> Hoy la única manera es:
> 1. `delete_tenant` con confirmación.
> 2. `deploy_tenant` con el nuevo tier.
>
> Significa **pérdida de datos** salvo backup previo. Roadmap: tool `change_tenant_tier` que solo patchee los `resources` y `ResourceQuota`.

→ Ver [[../12-Decisiones-Limitaciones/05-Futuro-roadmap#change_tenant_tier]].

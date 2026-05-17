---
title: Plantillas Jinja2 de tenants
tags: [tenants, jinja2, templates, manifests]
---

# 🎨 Plantillas Jinja2

> [!abstract] El YAML lo genera Jinja2, no el LLM
> Carpeta: `lobster_agent/manifests/`. `ManifestRenderer` carga la plantilla por tipo, sustituye variables con valores tipados (tier, hostname, imagen, …) y devuelve los documentos YAML parseados. El LLM **no escribe YAML** — solo elige qué plantilla con qué parámetros.

## 📂 Archivos

```text
lobster_agent/manifests/
├── wordpress.yaml.j2      → TenantType.WORDPRESS
├── static_site.yaml.j2    → TenantType.STATIC_SITE
└── web_app.yaml.j2        → TenantType.WEB_APP
```

## 🧬 `ManifestRenderer`

```python
class ManifestRenderer:
    def __init__(self, templates_dir=Path("lobster_agent/manifests")):
        self.env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(templates_dir),
            autoescape=False,
            undefined=jinja2.StrictUndefined,    # ← falla si falta variable
        )

    def render(self, tenant_type, context):
        template = self.env.get_template(f"{tenant_type.value}.yaml.j2")
        # Para WordPress: autogenera db_password si no viene
        if tenant_type == TenantType.WORDPRESS and "db_password" not in context:
            context["db_password"] = self.generate_db_password()
        if tenant_type == TenantType.WORDPRESS and "quota_limits" not in context:
            context["quota_limits"] = {...}     # duplicado
        text = template.render(**context)
        documents = [doc for doc in yaml.safe_load_all(text) if doc is not None]
        return documents     # list[dict]
```

## 🔑 Variables disponibles en plantillas

| Variable | Para qué | Ejemplo |
|---|---|---|
| `name` | nombre del tenant = namespace | `my-blog` |
| `tier` | tier string | `free` |
| `limits` | `TierLimits` dataclass | `TierLimits(cpu_request="50m", ...)` |
| `hostname` | dominio | `my-blog.saasphere.local` |
| `image` | (web_app) imagen Docker | `nginx:1.25` |
| `port` | puerto del contenedor | `80` |
| `env` | dict de env vars | `{"FOO": "bar"}` |
| `owner` | operador que despliega | `admin` |
| `admin_email` | (WordPress) email del admin | `me@example.com` |
| `db_password` | (WordPress) autogenerado | `<token base64>` |
| `quota_limits` | (WordPress) cuotas duplicadas | dict |

## 🔐 Seguridad de la generación

> [!info] `db_password` con `secrets.token_urlsafe(24)`
> Cada despliegue WordPress genera una contraseña aleatoria. Se persiste como `Secret` en el namespace del tenant. El operador puede recuperarla con:
> ```bash
> kubectl --kubeconfig=/etc/lobster/kubeconfig get secret my-blog-db -n my-blog -o jsonpath='{.data.password}' | base64 -d
> ```

> [!warning] `StrictUndefined`
> Si la plantilla referencia `{{ foo }}` y `foo` no está en el contexto, Jinja2 lanza error. Esto previene templates silenciosamente "vacíos".

## 🎯 Pasos de aplicación

`tools/mutations/tenant.py:deploy_tenant.executor`:

```python
for resource in _dependency_order(resources):
    applied.append(await k8s.apply_manifest(yaml.safe_dump(resource)))
```

Orden:
```python
order = {
    "Namespace": 0,
    "Secret": 1,
    "PersistentVolumeClaim": 2,
    "ResourceQuota": 3,
    "Deployment": 4,
    "Service": 5,
    "Ingress": 6,
}
```

> [!tip] Por qué ese orden
> - Namespace primero (todo lo demás necesita un ns).
> - Secret antes que Deployment (el deployment monta el secret).
> - PVC antes que Deployment (mount).
> - Service antes que Ingress (backend del ingress).

## 🛡️ Validación previa

```python
# Antes de pedir aprobación, valida cada recurso:
for resource in resources:
    decision = policy.validate(
        "apply_manifest",
        resource_namespace,
        manifest=resource,
        context={"namespace_labels": ..., "internal_tooling": True},
    )
    if not decision.allowed:
        return f"deploy_tenant rejected by policy: {decision.reason}"
```

> [!info] `internal_tooling=True`
> Permite que el Secret de la BD pase la policy (que de otro modo bloquearía cualquier `Secret`).

## 🚨 Si falla a mitad: rollback

```python
try:
    for resource in _dependency_order(resources):
        await k8s.apply_manifest(...)
except Exception:
    await k8s.delete_namespace(name)        # cascade delete
    raise
```

> [!warning] Cleanup automático
> Si aplicar el Deployment falla porque la imagen no existe, Lobster borra el Namespace entero (cascada elimina PVC, Service, todo). El operador queda con un mensaje claro y sin recursos huérfanos.

## 🎨 Ejemplo de fragmento Jinja2

```jinja
{% if not hostname.endswith('.saasphere.local') %}
    cert-manager.io/cluster-issuer: letsencrypt-prod
    traefik.ingress.kubernetes.io/router.entrypoints: websecure
{% else %}
    traefik.ingress.kubernetes.io/router.entrypoints: web
{% endif %}
```

→ Para ver las plantillas completas, abrir los archivos en `lobster_agent/manifests/`. Esta wiki **no las duplica** para evitar drift.

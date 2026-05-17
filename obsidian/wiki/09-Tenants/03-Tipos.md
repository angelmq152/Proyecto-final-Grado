---
title: Tipos — WordPress, Static, Web App
tags: [tenants, tipos, wordpress, static, webapp]
---

# 🏗️ Tipos de tenant

> [!abstract] Tres plantillas, tres caminos
> Cada tenant es de uno de **tres tipos**, cada uno con plantilla Jinja2 propia en `lobster_agent/manifests/`. La plantilla define qué recursos K8s se crean.

## 🍷 WordPress · `wordpress.yaml.j2`

> [!info] WordPress + MariaDB completo
> Crea **9 recursos**:
> 1. Namespace con labels.
> 2. Secret con db_password (autogenerado).
> 3. PVC para WordPress (`{{ name }}-wordpress`, RWO local-path).
> 4. PVC para MariaDB (`{{ name }}-mariadb`).
> 5. ResourceQuota (cuotas duplicadas para 2 pods).
> 6. Deployment MariaDB (1 replica, imagen `mariadb:10.11`).
> 7. Service MariaDB (ClusterIP :3306).
> 8. Deployment WordPress (`limits.replicas` replicas, imagen `wordpress:latest`).
> 9. Service WordPress (ClusterIP :80).
> 10. Ingress con TLS condicional.

> [!warning] Requiere `admin_email`
> Validación temprana en `deploy_tenant`:
> ```python
> if parsed_type == TenantType.WORDPRESS and not admin_email:
>     return "deploy_tenant failed before action creation: wordpress requires admin_email"
> ```

> [!example] Mensaje final
> *"tenant deployed: https://my-blog.saasphere.local; admin: https://my-blog.saasphere.local/wp-admin"*

## 📄 Static site · `static_site.yaml.j2`

> [!info] HTML estático + nginx
> Crea **6 recursos**:
> 1. Namespace.
> 2. PVC `{{ name }}-html` (1Gi en FREE).
> 3. ResourceQuota.
> 4. Deployment con `nginx:alpine`, monta el PVC en `/usr/share/nginx/html`.
> 5. Service ClusterIP :80.
> 6. Ingress con TLS condicional.

> [!tip] hostPath para subir contenido
> El executor espera el PVC bound y lee el `hostPath` del PV asignado:
> ```python
> if parsed_type == TenantType.STATIC_SITE:
>     await wait_for_pvc_bound(name, f"{name}-html", timeout_seconds=30)
>     host_path = await get_pvc_host_path(name, f"{name}-html")
> ```
> El mensaje al operador incluye:
> *"tenant deployed: https://...; scp target: matrix:/var/lib/rancher/k3s/storage/pvc-abc.../"*
> El operador hace `scp index.html matrix:<host_path>/` y listo.

## 📦 Web app · `web_app.yaml.j2`

> [!info] Aplicación custom (imagen Docker)
> Crea **4 recursos**:
> 1. Namespace.
> 2. ResourceQuota.
> 3. Deployment con la imagen y puerto pasados como parámetros + env vars opcionales.
> 4. Service ClusterIP `:{{ port }}`.
> 5. Ingress.

> [!warning] Requiere `image` y opcionalmente `env`
> ```python
> if parsed_type == TenantType.WEB_APP and not image:
>     return "deploy_tenant failed before action creation: web_app requires image"
> ```

> [!example] Despliegue con env
> ```python
> deploy_tenant(
>     tenant_type="web_app",
>     name="api-orders",
>     tier="basic",
>     image="ghcr.io/me/api:1.2.3",
>     port=3000,
>     env={"DATABASE_URL": "postgres://...", "LOG_LEVEL": "info"},
>     admin_email=None,
> )
> ```

## 🆚 Comparativa

| Aspecto | WordPress | Static | Web app |
|---|---|---|---|
| Recursos generados | 9 | 6 | 4 |
| Pods activos | 2 (WP + MariaDB) | 1 | 1+ replicas |
| PVCs | 2 | 1 | 0 |
| Almacenamiento | DB + uploads | HTML | none por defecto |
| TLS | Sí (si dominio real) | Sí | Sí |
| Imagen | wordpress:latest + mariadb:10.11 | nginx:alpine | custom |
| Requiere admin_email | ✅ | ❌ | ❌ |
| Requiere image | ❌ | ❌ | ✅ |

## 🔢 Tipos en código

```python
class TenantType(StrEnum):
    WORDPRESS = "wordpress"
    STATIC_SITE = "static_site"
    WEB_APP = "web_app"
```

## 🧬 Cómo elegir

> [!tip] Pregunta antes de actuar
> El system prompt incluye:
> *"deploy_tenant despliega una web nueva. Es CRITICA y requiere aprobacion. Si el usuario pide una web sin especificar tipo, pregunta antes: estatica (HTML), wordpress, o aplicacion custom (imagen Docker)."*

→ Sigue en [[04-Plantillas-Jinja2]].

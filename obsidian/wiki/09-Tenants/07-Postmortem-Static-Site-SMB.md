---
title: Postmortem — Tenants estáticos sobre SMB
tags: [tenants, postmortem, smb, csi, storage, incidente, debug]
---

# 🦞 Postmortem · Tenants estáticos sobre SMB

> [!abstract] Cómo terminamos con `StorageClass` + `subDir` plantillado tras descartar cuatro alternativas
> Durante una sesión larga (2026-05-22 → 2026-05-23) reescribimos cómo los tenants `static_site` exponen contenido HTML al usuario. El objetivo era trivial — *"dejo un index.html en una carpeta de LeIA y nginx lo sirve"* — pero la combinación de cluster multi-nodo, hardening de systemd, política de Lobster y alucinaciones del modelo nos llevó por cinco enfoques distintos. Este documento captura el camino completo para que nunca tengamos que volver a recorrerlo.

## 🎯 Objetivo del usuario

> *"Tiene que ser jodidamente simple y que se haga subiendo a una carpeta local de LeIA, esa era la intención."*  
> *"En leia no se tiene que ejecutar NADA."*

Traducido a requisitos:

1. **Predecibilidad** del path donde dejar archivos: debe contener el nombre del tenant.
2. **Cero workload** en LeIA (control-plane con taint `NoSchedule`).
3. **Acceso multi-nodo** desde matrix/fallback (donde corren los pods).
4. **Cero intervención manual** tras `deploy_tenant`.

## 🧭 Topología relevante

```text
                    +-----------------------------+
                    |          LeIA               |
                    |  192.168.1.200              |
                    |                             |
                    |  - k3s control-plane        |
                    |    (taint NoSchedule)       |
                    |  - Samba server             |
                    |    share [k3s-pvs]          |
                    |    path /srv/k3s-pvs        |
                    |  - lobster.service          |
                    |    User=openclaw            |
                    |    ProtectSystem=strict     |
                    +-------------+---------------+
                                  |  SMB 192.168.1.200/k3s-pvs
                                  |
              +-------------------+--------------------+
              |                                        |
   +----------v-----------+               +------------v-----------+
   |       matrix          |              |        fallback         |
   |  saasphere.io/workload|              |   saasphere.io/workload |
   |  csi-smb-node-*       |              |   csi-smb-node-*        |
   |  pods static_site     |              |   pods static_site      |
   +-----------------------+              +-------------------------+
```

## ❌ Enfoques descartados

> [!warning] Cuatro callejones sin salida — uno por uno
> Cada intento solucionaba una arista del problema pero rompía otra.

### 1. `hostPath` apuntando a LeIA

| Aspecto         | Detalle                                                                                |
| --------------- | -------------------------------------------------------------------------------------- |
| Idea            | Cada pod monta `/srv/lobster/static/<name>/html/` directamente del nodo donde corre    |
| Por qué falló   | Los pods corren en matrix/fallback, no en LeIA → leen una carpeta vacía → **403 Nginx** |
| Coste colateral | Tuvimos que añadir excepción `_ALLOWED_HOST_PATHS` en `policy.py`                       |
| Verdict         | No funciona en multi-nodo. Descartado de raíz.                                          |

### 2. ConfigMap volume

| Aspecto         | Detalle                                                              |
| --------------- | -------------------------------------------------------------------- |
| Idea            | Plantilla Jinja renderiza un ConfigMap con `index.html` embebido     |
| Por qué falló   | Rompe el requisito *"subir a una carpeta"* — el usuario debe regenerar el ConfigMap |
| Comando feo     | `kubectl create configmap ... --from-file=... --dry-run -o yaml \| kubectl apply -f -` |
| Verdict         | Funciona, pero rompe la UX que el usuario pidió. Descartado.         |

### 3. SMB CSI dinámico con UUID

| Aspecto         | Detalle                                                                                 |
| --------------- | --------------------------------------------------------------------------------------- |
| Idea            | PVC con `storageClassName: smb-saasphere` (preexistente) → driver crea subdir aleatorio |
| Path generado   | `/srv/k3s-pvs/pvc-<uuid>/` — **no contiene el nombre del tenant**                       |
| Por qué falló   | Imposible que el usuario adivine la ruta. Tras el deploy hay que consultar el PV.       |
| Verdict         | Funcional pero opaco. Descartado por UX.                                                |

### 4. PV estático cluster-scoped con source SMB explícito

| Aspecto       | Detalle                                                                                  |
| ------------- | ---------------------------------------------------------------------------------------- |
| Idea          | Cada tenant tiene su `PersistentVolume` con `source: //leia/k3s-pvs/lobster-static/<n>/html` |
| Path          | Predecible: `/srv/k3s-pvs/lobster-static/<name>/html/` ✅                                  |
| Por qué falló | Cascada de **5 problemas distintos** que descubrimos uno por uno (siguiente sección)     |
| Verdict       | Acertado en filosofía, frágil en ejecución. Sustituido por StorageClass templated.       |

## 🔥 Cascada de errores con el PV estático

> [!example] Cada error tapaba al siguiente
> El rollback enmascaraba la causa raíz, y al arreglar uno aparecía otro.

```
deploy_tenant("pepito")
 │
 ├─ [1] _dependency_order no incluía "PersistentVolume" → orden 99 → PVC se aplica antes que PV
 │       FIX: añadir "PersistentVolume": 2 en order dict
 │
 ├─ [2] try/except del executor llamaba delete_namespace en rollback
 │       Cuando el fallo era previo al apply de Namespace, rollback fallaba
 │       con "namespace not found" → ENMASCARABA el error real
 │       FIX: flag namespace_created + try/except dentro del rollback
 │
 ├─ [3] mkdir /srv/k3s-pvs/lobster-static/pepito/html → PermissionError
 │       Causa: /srv/k3s-pvs era drwxrwx--- angel:angel
 │       openclaw no estaba en grupo angel → ni siquiera podía atravesar
 │       FIX: setfacl -m u:openclaw:x /srv/k3s-pvs
 │
 ├─ [4] mkdir → "Read-only file system"
 │       Causa: lobster.service tiene ProtectSystem=strict
 │       Solo /var/lib/lobster, /var/log/lobster, /opt/openclaw/obsidian son rw
 │       /srv/k3s-pvs aparece read-only desde el namespace mount del servicio
 │       Workaround posible: añadir ReadWritePaths=/srv/k3s-pvs/lobster-static
 │       Pero requiere drop-in systemd y otro restart
 │
 └─ [5] apply_manifest(PV) → "Manifest kind is not allowed: PersistentVolume"
         Causa: ALLOWED_MANIFEST_KINDS en clients/k8s.py es allowlist hardcoded
         FIX: añadir "PersistentVolume" al set
```

> [!tip] Aprendizaje meta-técnico
> El rollback `await ctx.deps.k8s.delete_namespace(name)` sin protección **escondió el error real durante tres iteraciones**. El usuario veía *"namespace not found"* y el modelo qwen3:8b lo interpretaba como una restricción de política inexistente. **Cualquier rollback debe ir envuelto en try/except** para que la excepción original se propague.

## ✅ Solución definitiva: StorageClass con `subDir` plantillado

> [!abstract] Una sola pieza nueva, cero código del agente toca el filesystem
> El driver `smb.csi.k8s.io` soporta plantillas Go en el parámetro `subDir`. Le delegamos la creación del subdirectorio durante `CreateVolume`. Lobster se vuelve a limitar a aplicar manifests namespaced.

### 1. La StorageClass

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: smb-lobster-static
provisioner: smb.csi.k8s.io
reclaimPolicy: Retain
volumeBindingMode: Immediate
allowVolumeExpansion: true
mountOptions:
  - dir_mode=0777
  - file_mode=0777
  - uid=1000
  - gid=1000
  - noperm
  - vers=3.0
parameters:
  source: "//192.168.1.200/k3s-pvs"
  subDir: "lobster-static/${pvc.metadata.namespace}/html"
  csi.storage.k8s.io/node-stage-secret-name: smb-credentials
  csi.storage.k8s.io/node-stage-secret-namespace: kube-system
  csi.storage.k8s.io/provisioner-secret-name: smb-credentials
  csi.storage.k8s.io/provisioner-secret-namespace: kube-system
```

Clave: el `${pvc.metadata.namespace}` se sustituye en runtime por el driver. PVC `langosta-html` en namespace `langosta` resuelve a subdir `lobster-static/langosta/html`.

### 2. El manifest del tenant (`static_site.yaml.j2`)

Resultado renderizado para `name=pepinillo`:

```yaml
apiVersion: v1
kind: Namespace
metadata: { name: pepinillo, labels: { saasphere.io/tenant: "true", ... } }
---
apiVersion: v1
kind: ResourceQuota
metadata: { name: pepinillo-quota, namespace: pepinillo }
spec:
  hard:
    requests.cpu: "50m"
    limits.cpu: "200m"
    requests.memory: "64Mi"
    limits.memory: "256Mi"
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata: { name: pepinillo-html, namespace: pepinillo }
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: smb-lobster-static    # ← clave
  resources: { requests: { storage: 1Gi } }
---
apiVersion: apps/v1
kind: Deployment
metadata: { name: pepinillo, namespace: pepinillo }
spec:
  replicas: 1
  strategy: { type: Recreate }            # ← evita deadlock con ResourceQuota
  template:
    spec:
      affinity:                           # ← excluye LeIA
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
              - matchExpressions:
                  - { key: saasphere.io/workload, operator: In, values: ["true"] }
      containers:
        - name: nginx
          image: nginx:alpine
          volumeMounts: [{ name: html, mountPath: /usr/share/nginx/html }]
      volumes:
        - name: html
          persistentVolumeClaim: { claimName: pepinillo-html }
---
# Service ClusterIP + Ingress traefik (web entrypoint para .saasphere.local)
```

Nota: **ya no hay PV cluster-scoped**, solo PVC namespaced.

### 3. El executor (`tenant.py`)

```python
async def executor() -> dict[str, Any]:
    namespace_created = False
    try:
        applied: list[dict[str, str]] = []
        for resource in _dependency_order(resources):
            applied.append(await ctx.deps.k8s.apply_manifest(yaml.safe_dump(resource)))
            if resource.get("kind") == "Namespace":
                namespace_created = True
        html_path = (
            STATIC_TENANT_PATH.format(name=name)
            if parsed_type == TenantType.STATIC_SITE
            else None
        )
        return {"applied": applied, "url": f"https://{hostname}", "html_path": html_path}
    except Exception:
        if namespace_created:
            try:
                await ctx.deps.k8s.delete_namespace(name)
            except Exception:
                pass
        raise
```

Lobster **no toca `/srv/k3s-pvs`** en absoluto. Solo aplica YAMLs y calcula la ruta para el mensaje (es un f-string, no un mkdir).

### 4. Flujo de creación end-to-end

```
Usuario (Telegram)
  │ "Crea un tenant estático llamado pepinillo"
  ▼
Lobster (caso de uso CHAT → tool deploy_tenant)
  │ render Jinja → 6 recursos
  │ policy.validate(each)
  │ MutationContext.execute(severity=CRITICAL)
  │   → Telegram approval → ✅
  │   → executor():
  │       kubectl apply Namespace, ResourceQuota, PVC, Deployment, Service, Ingress
  ▼
k8s controller-manager
  │ ve PVC en pending → busca StorageClass smb-lobster-static
  │ llama al CSI controller (provisioner)
  ▼
csi-smb-controller pod
  │ CreateVolume:
  │   - resuelve subDir template → "lobster-static/pepinillo/html"
  │   - monta //192.168.1.200/k3s-pvs temporalmente
  │   - mkdir lobster-static/pepinillo/html  (en LeIA, via SMB)
  │   - crea PV pvc-<uuid> con volumeAttributes.subDir
  ▼
k8s scheduler
  │ asigna pod a matrix o fallback (nodeAffinity workload=true)
  ▼
csi-smb-node-<node>
  │ NodeStageVolume: mount.cifs //leia/k3s-pvs/lobster-static/pepinillo/html
  │   → /var/lib/kubelet/.../globalmount
  │ NodePublishVolume: bind mount → pod's /usr/share/nginx/html
  ▼
nginx:alpine
  │ sirve archivos de /usr/share/nginx/html
  │ (vacío al inicio → 403 hasta que el usuario suba index.html)
  ▼
Usuario deja index.html en /srv/k3s-pvs/lobster-static/pepinillo/html/
  │ (vía SCP, samba mount desde su PC, o editor local en LeIA)
  ▼
nginx lo sirve inmediatamente (SMB es coherente, no hay caché)
```

## 🧪 Verificación operada (2026-05-23)

> [!example] Doble validación: tenant antiguo migrado + tenant nuevo desde cero

### Langosta (migración)

```bash
# Estado previo: PV estático bound a PVC en /srv/k3s-pvs/lobster-static/langosta/html
kubectl delete pvc langosta-html -n langosta --wait=false
kubectl scale deployment langosta -n langosta --replicas=0  # libera el mount
kubectl delete pv lobster-static-langosta

# Aplicar nueva PVC con StorageClass templated
kubectl apply -f - <<EOF
apiVersion: v1
kind: PersistentVolumeClaim
metadata: { name: langosta-html, namespace: langosta }
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: smb-lobster-static
  resources: { requests: { storage: 1Gi } }
EOF

kubectl scale deployment langosta -n langosta --replicas=1
curl -s -o /dev/null -w "%{http_code}\n" \
  --resolve langosta.saasphere.local:80:192.168.1.240 \
  http://langosta.saasphere.local/
# → 200 (sirve el index.html del usuario, preservado en el FS)
```

### Pepinillo (creación desde Telegram con Lobster reiniciado)

```text
Pod:     pepinillo-5c5bc94ccd-cq9bq Running en fallback, 0 restarts
PVC:     pepinillo-html Bound a pvc-79912bbe-... via smb-lobster-static
Ingress: pepinillo.saasphere.local → 192.168.1.240
Dir LeIA: /srv/k3s-pvs/lobster-static/pepinillo/html/ (creado por el driver)
HTTP:    200 OK
Logs:    nginx 1.31.0, GET / 200 4342 bytes
```

## 🩺 Errores secundarios que también arreglamos

| Bug | Causa | Fix |
|---|---|---|
| Tests rompían en `/srv/k3s-pvs` real | `tenant.py` hacía mkdir en path absoluto durante tests unitarios | Env var `LOBSTER_STATIC_ROOT` + fixture autouse (eliminado al final cuando ya no hay mkdir) |
| Pods estáticos antiguos competían por ResourceQuota durante rolling update | `strategy: RollingUpdate` quería 2 pods simultáneos, quota permitía 1 | `strategy: Recreate` |
| Pods aterrizando en LeIA tras `kubectl scale` | Faltaba nodeAffinity en deployment | Añadido `saasphere.io/workload=true` requiredDuringScheduling |
| Watcher de Lobster spammeaba sobre `smb-test` que ya no existía | Eventos K8s permanecen ~1h tras el delete | `kubectl delete events --field-selector involvedObject.name=smb-test` |
| Modelo qwen3:8b inventaba "no se permiten PVCs" | El error real era K8sClientError, hallucination en chat | El log auténtico siempre vía `uv run lobster actions show <id>` |
| Test `test_pause_and_resume_change_state` esperaba DRY_RUN | Handler se cambió a PAUSED (más semántico) sin actualizar el test | Test sincronizado a `AgentMode.PAUSED` |

## 🧠 Lecciones para futuras incidencias

> [!tip] Cinco reglas que valen para cualquier mutación de Lobster

1. **El rollback siempre va en try/except.** Cualquier limpieza que falle debe swallowearse para no enmascarar la excepción original.
2. **Cuando Lobster da un error raro, ignora la respuesta del LLM** y vete a la fuente: `uv run lobster actions show <id>` o `journalctl -u lobster`. El modelo de chat traduce mal y a veces fantasea.
3. **Hardening de systemd es invisible hasta que muerde.** `ProtectSystem=strict` no aparece en `kubectl describe pod` ni en logs del agente — solo en `EROFS` al hacer `mkdir`. Lista mental antes de añadir rutas nuevas: ¿está en `ReadWritePaths`?
4. **Si el agente puede delegar al cluster, hazlo.** El driver SMB-CSI ya sabe hacer mkdir; meter Python entre medias añade superficie de fallo (permisos, hardening, idempotencia, rollback).
5. **Modelo multi-nodo: hostPath está muerto.** Cualquier persistencia tenant que necesite ser visible por pods en cualquier nodo tiene que ir por SMB/NFS/PVC. No hay otra.

## 🔗 Relacionado

- [[04-Plantillas-Jinja2|Plantillas Jinja2 de tenants]] — donde vive `static_site.yaml.j2`
- [[05-Ciclo-de-vida|Ciclo de vida de tenants]] — flujo deploy/delete/pause/resume
- [[06-Politica-namespaces|Política de namespaces]] — qué bloquea Lobster y qué no
- [[../10-Operacion/07-Troubleshooting|Troubleshooting]] — síntomas y remedios habituales
- [[../12-Decisiones-Limitaciones/01-Decisiones-arquitectura|Decisiones de arquitectura]] — registro de ADRs

## 📅 Cronología

| Hora (CEST) | Evento |
|---|---|
| 2026-05-22 19:00 | Usuario reporta 403 en langosta tras dejar index.html en `/srv/lobster/static/langosta/html/` |
| 2026-05-22 20:00 | Descartado hostPath (multi-nodo) |
| 2026-05-22 21:00 | Probado ConfigMap (rechazado por UX) |
| 2026-05-22 22:00 | Probado SMB dinámico (UUID feo) |
| 2026-05-22 23:00 | Probado PV estático — cascada de 5 errores empieza |
| 2026-05-23 00:15 | Identificada la raíz arquitectónica: Lobster no debería tocar el FS host |
| 2026-05-23 00:25 | StorageClass `smb-lobster-static` desplegada, manifest reescrito, langosta migrada |
| 2026-05-23 00:32 | Pepinillo creado desde Telegram, 200 OK al primer intento |
| 2026-05-23 00:40 | Postmortem documentado en Obsidian (este documento) |

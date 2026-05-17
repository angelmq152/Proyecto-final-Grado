## 🗺️ Contexto

|Parámetro|Valor|
|---|---|
|Fase|Orquestación (post-install)|
|Nodo|Matrix — `192.168.1.202`|
|Cluster|K3s server único (HA pendiente con 2 VPS)|
|CNI actual|Flannel (default K3s)|
|Ingress|Traefik con Let's Encrypt|
|Registry|`matrix:5000` (Registry v2 privado)|
|Runtime|containerd|
|Base previa|`k3s_matrix.md` ya aplicado|

> [!info] Alcance de este documento `k3s_matrix.md` cubre el **bootstrap** (instalar K3s, Docker, Registry, Traefik, RBAC LeIA). Este documento cubre la **capa de orquestación**: convenciones, aislamiento, políticas, plantillas reutilizables y un despliegue end-to-end de validación. Al terminar, el clúster está listo para recibir clientes reales desplegados por LeIA.

> [!warning] Requisito previo Ejecutar y verificar `k3s_matrix.md` antes de seguir. Sin el bootstrap no hay nada sobre lo que orquestar.

---

## 🏗️ Arquitectura de orquestación

```
Internet
   │ :80 / :443  (port-forwarding router → Matrix)
   ▼
┌────────────────────────────────────────────┐
│ Matrix (K3s server + containerd)           │
│                                            │
│  ┌─ kube-system ───────────────────────┐   │
│  │ traefik · coredns · metrics-server  │   │
│  │ kube-state-metrics  (se añade aquí) │   │
│  └─────────────────────────────────────┘   │
│                                            │
│  ┌─ saasphere-system ──────────────────┐   │
│  │ leia-agent (SA) · rbac              │   │
│  │ (infra interna, no clientes)        │   │
│  └─────────────────────────────────────┘   │
│                                            │
│  ┌─ cliente-demo ──────────────────────┐   │
│  │ Deployment · Service · Ingress · PVC│   │
│  │ ResourceQuota · LimitRange · NetPol │   │
│  └─────────────────────────────────────┘   │
│                                            │
│  ┌─ cliente-<N> (creado por LeIA) ─────┐   │
│  │ misma plantilla, datos aislados     │   │
│  └─────────────────────────────────────┘   │
└────────────────────────────────────────────┘
```

### Convenciones de naming y etiquetado

|Elemento|Patrón|Ejemplo|
|---|---|---|
|Namespace de cliente|`cliente-<slug>`|`cliente-acme`|
|Deployment|`<slug>-<componente>`|`acme-web`, `acme-api`|
|Service|mismo nombre que el Deployment|`acme-web`|
|Ingress|`<slug>-ingress`|`acme-ingress`|
|PVC|`<slug>-<rol>-data`|`acme-web-data`|
|Imagen en registry|`matrix:5000/<slug>-<componente>:<tag>`|`matrix:5000/acme-web:v1`|

Labels obligatorios en todos los recursos de cliente:

```yaml
labels:
  saasphere.io/tenant: <slug>          # acme
  saasphere.io/component: <componente> # web | api | worker
  saasphere.io/managed-by: leia        # o "manual" si se despliega a mano
```

> [!tip] Por qué el label `managed-by` Permite filtrar en Grafana y en `kubectl` entre workloads gestionados por LeIA y los que se desplieguen manualmente para pruebas. También deja sitio para un futuro GitOps (`managed-by: argocd`) sin renombrar nada.

---

## 🧠 Decisión abierta — CNI y NetworkPolicies

> [!danger] Flannel **no** aplica NetworkPolicies K3s viene con Flannel por defecto. Flannel da red pod-a-pod pero **ignora** los recursos `NetworkPolicy`. Esto significa que, tal como está el clúster hoy, un pod del `cliente-acme` puede hablar con un pod del `cliente-bob` sin restricciones. Para una SaaS multitenant esto es inaceptable a medio plazo.

**Opciones sobre la mesa:**

|Opción|Pros|Contras|
|---|---|---|
|**A.** Mantener Flannel, aceptar limitación|Cero trabajo extra, cluster ya montado|Aislamiento real solo a nivel de Ingress (Traefik). Un pod comprometido ve todo. No es defendible como "production-credible" en la memoria del TFG.|
|**B.** Reinstalar con `--flannel-backend=none` + **Cilium**|NetworkPolicies + eBPF observability + Hubble. Enfoque moderno y estándar de facto en 2026.|Reinstalar K3s, re-pushear imágenes, reaplicar manifiestos. Trabajo de 1-2 horas bien ejecutado.|
|**C.** Flannel + **kube-router** solo para policies|Menos invasivo que Cilium|kube-router está menos activo, menos documentado, menor valor en un TFG.|

> [!note] Recomendación **Opción B — Cilium.** El TFG gana un argumento arquitectónico fuerte ("elegí Cilium por NetworkPolicies + eBPF + observabilidad de tráfico"), y dejas la puerta abierta a Hubble para visualizar el tráfico entre namespaces en el tribunal. El coste de reinstalar ahora (cluster vacío) es mínimo comparado con hacerlo cuando ya haya clientes reales.

**Decisión pendiente:** fijar opción antes de desplegar `cliente-demo`. Este documento continúa asumiendo **opción A** (Flannel) y marca con ⚡ los puntos que cambiarían con Cilium.

---

## 📦 Fase 0 — Pre-flight: verificar bootstrap

```bash
# Cluster vivo
kubectl get nodes -o wide
# matrix   Ready   control-plane,master   ...   Debian GNU/Linux 13

# Pods de sistema
kubectl get pods -A
# kube-system: traefik · coredns · metrics-server · local-path-provisioner
# saasphere-system: (vacío, ok)

# Traefik con ACME configurado
kubectl -n kube-system describe pod -l app.kubernetes.io/name=traefik \
  | grep -A2 "letsencrypt"

# Registry accesible desde el nodo
curl -s http://matrix:5000/v2/_catalog
# {"repositories":[]}

# RBAC de LeIA aplicado
kubectl get sa leia-agent -n saasphere-system
kubectl get clusterrole leia-role
kubectl get clusterrolebinding leia-rolebinding
```

> [!success] Si todo responde Se puede avanzar a la Fase 1. Si algo falla, volver a `k3s_matrix.md`.

---

## ⚙️ Fase 1 — IngressClass y finalización de Traefik

K3s registra Traefik como IngressClass pero **no** la marca como default. Esto obliga a especificar `ingressClassName: traefik` en cada Ingress. Hacerla default simplifica los manifiestos de cliente.

```bash
kubectl get ingressclass
# NAME      CONTROLLER                      PARAMETERS   AGE
# traefik   traefik.io/ingress-controller   <none>       ...

kubectl annotate ingressclass traefik \
  ingressclass.kubernetes.io/is-default-class=true --overwrite

kubectl get ingressclass traefik -o yaml | grep default-class
# ingressclass.kubernetes.io/is-default-class: "true"
```

> [!tip] Efecto Cualquier Ingress que no especifique `ingressClassName` pasará automáticamente por Traefik. Un Ingress puede seguir declarándolo explícitamente si se quiere ser estricto.

---

## 🔐 Fase 2 — Hardening del namespace `saasphere-system`

El namespace ya existe. Añadimos **Pod Security Admission** en modo `restricted` para bloquear privilegios innecesarios en los workloads de infraestructura interna.

```bash
kubectl label namespace saasphere-system \
  pod-security.kubernetes.io/enforce=restricted \
  pod-security.kubernetes.io/enforce-version=latest \
  pod-security.kubernetes.io/audit=restricted \
  pod-security.kubernetes.io/warn=restricted \
  --overwrite

kubectl get ns saasphere-system --show-labels
```

> [!note] Por qué `restricted` aquí y no en los namespaces de cliente `saasphere-system` aloja solo infra controlada por nosotros (kube-state-metrics, exporters, agentes internos). Los namespaces de cliente reciben imágenes de terceros que pueden requerir `baseline`; se decide por cliente en la plantilla.

---

## 🧩 Fase 3 — Plantilla de namespace de cliente

Crear la plantilla reutilizable que LeIA (y nosotros en pruebas) aplicarán por cada cliente nuevo. Variables a sustituir:

- `{{SLUG}}` — identificador del cliente (ej. `acme`, `demo`).
- `{{CPU_LIMIT}}` — por defecto `2`.
- `{{MEM_LIMIT}}` — por defecto `4Gi`.
- `{{MAX_PODS}}` — por defecto `10`.

```bash
mkdir -p /opt/k3s/templates
cat > /opt/k3s/templates/cliente-namespace.yaml << 'EOF'
---
apiVersion: v1
kind: Namespace
metadata:
  name: cliente-{{SLUG}}
  labels:
    saasphere.io/tenant: "{{SLUG}}"
    saasphere.io/managed-by: leia
    pod-security.kubernetes.io/enforce: baseline
    pod-security.kubernetes.io/audit: restricted
    pod-security.kubernetes.io/warn: restricted
---
apiVersion: v1
kind: ResourceQuota
metadata:
  name: tenant-quota
  namespace: cliente-{{SLUG}}
spec:
  hard:
    requests.cpu: "{{CPU_LIMIT}}"
    requests.memory: "{{MEM_LIMIT}}"
    limits.cpu: "{{CPU_LIMIT}}"
    limits.memory: "{{MEM_LIMIT}}"
    pods: "{{MAX_PODS}}"
    persistentvolumeclaims: "5"
    services.loadbalancers: "0"
    services.nodeports: "0"
---
apiVersion: v1
kind: LimitRange
metadata:
  name: tenant-limits
  namespace: cliente-{{SLUG}}
spec:
  limits:
    - type: Container
      default:
        cpu: "500m"
        memory: "512Mi"
      defaultRequest:
        cpu: "100m"
        memory: "128Mi"
---
# NetworkPolicy - default deny all ingress
# ⚡ SOLO TIENE EFECTO REAL CON CILIUM (Flannel la ignora)
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-ingress
  namespace: cliente-{{SLUG}}
spec:
  podSelector: {}
  policyTypes: ["Ingress"]
---
# Allow Traefik ingress controller to reach pods of this tenant
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-traefik-ingress
  namespace: cliente-{{SLUG}}
spec:
  podSelector: {}
  policyTypes: ["Ingress"]
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
          podSelector:
            matchLabels:
              app.kubernetes.io/name: traefik
EOF
```

Script de instanciación (opcional, facilita las pruebas manuales):

```bash
cat > /opt/k3s/templates/new-tenant.sh << 'EOF'
#!/usr/bin/env bash
set -euo pipefail

SLUG="${1:?uso: new-tenant.sh <slug> [cpu] [mem] [pods]}"
CPU="${2:-2}"
MEM="${3:-4Gi}"
PODS="${4:-10}"

sed -e "s/{{SLUG}}/${SLUG}/g" \
    -e "s/{{CPU_LIMIT}}/${CPU}/g" \
    -e "s/{{MEM_LIMIT}}/${MEM}/g" \
    -e "s/{{MAX_PODS}}/${PODS}/g" \
    /opt/k3s/templates/cliente-namespace.yaml \
  | kubectl apply -f -

echo "Tenant cliente-${SLUG} listo."
EOF
chmod +x /opt/k3s/templates/new-tenant.sh
```

---

## 💾 Fase 4 — Verificación del storage (local-path)

K3s incluye `local-path-provisioner` como StorageClass por defecto. Verificar y promoverla como `default` explícito:

```bash
kubectl get storageclass
# NAME                   PROVISIONER             RECLAIMPOLICY  ...
# local-path (default)   rancher.io/local-path   Delete         ...

# Si no figura (default), marcarla:
kubectl patch storageclass local-path -p \
  '{"metadata": {"annotations":{"storageclass.kubernetes.io/is-default-class":"true"}}}'
```

> [!warning] Limitación de `local-path` Los datos viven en el filesystem de Matrix (`/var/lib/rancher/k3s/storage`). Si Matrix se cae y Fallback asume workloads, **los PVCs no migran**. Es el punto que alimenta la siguiente decisión de arquitectura: backups periódicos del directorio de storage + restore en Fallback. Se trata en la fase de HA con VPS.

Probar con un PVC efímero:

```bash
cat <<'EOF' | kubectl apply -f -
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: test-pvc
  namespace: default
spec:
  accessModes: ["ReadWriteOnce"]
  resources:
    requests:
      storage: 100Mi
EOF

kubectl get pvc test-pvc
# STATUS debe quedar Bound tras unos segundos (el volumen se crea al montarse)
# Si aparece Pending, es normal hasta que un pod lo reclame.

kubectl delete pvc test-pvc
```

---

## 📦 Fase 5 — Integración del registry privado (prueba funcional)

Validar el flujo tag → push → pull desde K3s:

```bash
# Imagen pública de prueba
docker pull nginx:alpine

# Re-tag apuntando al registry privado
docker tag nginx:alpine matrix:5000/demo-web:v1

# Push
docker push matrix:5000/demo-web:v1

# Verificar en el catálogo
curl -s http://matrix:5000/v2/_catalog
# {"repositories":["demo-web"]}

curl -s http://matrix:5000/v2/demo-web/tags/list
# {"name":"demo-web","tags":["v1"]}
```

> [!tip] Confirmación de pull desde K3s El pull real se valida en la Fase 7 cuando el Deployment de `cliente-demo` referencie esta misma imagen.

---

## 🚀 Fase 6 — Plantilla de aplicación (Deployment + Service + Ingress + PVC)

Base para cualquier workload de cliente. Variables:

- `{{SLUG}}` — slug del cliente
- `{{COMPONENT}}` — nombre del componente (web, api, etc.)
- `{{IMAGE}}` — imagen completa (ej. `matrix:5000/demo-web:v1`)
- `{{HOST}}` — hostname público (ej. `demo.tudominio.com`)
- `{{PORT}}` — puerto interno del contenedor
- `{{STORAGE}}` — tamaño del volumen (ej. `1Gi`)

```bash
cat > /opt/k3s/templates/cliente-app.yaml << 'EOF'
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: {{SLUG}}-{{COMPONENT}}-data
  namespace: cliente-{{SLUG}}
  labels:
    saasphere.io/tenant: "{{SLUG}}"
    saasphere.io/component: "{{COMPONENT}}"
    saasphere.io/managed-by: leia
spec:
  accessModes: ["ReadWriteOnce"]
  resources:
    requests:
      storage: {{STORAGE}}
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{SLUG}}-{{COMPONENT}}
  namespace: cliente-{{SLUG}}
  labels:
    saasphere.io/tenant: "{{SLUG}}"
    saasphere.io/component: "{{COMPONENT}}"
    saasphere.io/managed-by: leia
spec:
  replicas: 1
  selector:
    matchLabels:
      saasphere.io/tenant: "{{SLUG}}"
      saasphere.io/component: "{{COMPONENT}}"
  template:
    metadata:
      labels:
        saasphere.io/tenant: "{{SLUG}}"
        saasphere.io/component: "{{COMPONENT}}"
        saasphere.io/managed-by: leia
    spec:
      containers:
        - name: app
          image: {{IMAGE}}
          imagePullPolicy: IfNotPresent
          ports:
            - containerPort: {{PORT}}
          resources:
            requests:
              cpu: "100m"
              memory: "128Mi"
            limits:
              cpu: "500m"
              memory: "512Mi"
          volumeMounts:
            - name: data
              mountPath: /data
          securityContext:
            allowPrivilegeEscalation: false
            runAsNonRoot: false   # nginx:alpine corre como root; baseline lo permite
            capabilities:
              drop: ["ALL"]
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: {{SLUG}}-{{COMPONENT}}-data
---
apiVersion: v1
kind: Service
metadata:
  name: {{SLUG}}-{{COMPONENT}}
  namespace: cliente-{{SLUG}}
  labels:
    saasphere.io/tenant: "{{SLUG}}"
    saasphere.io/component: "{{COMPONENT}}"
spec:
  selector:
    saasphere.io/tenant: "{{SLUG}}"
    saasphere.io/component: "{{COMPONENT}}"
  ports:
    - port: 80
      targetPort: {{PORT}}
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {{SLUG}}-ingress
  namespace: cliente-{{SLUG}}
  annotations:
    traefik.ingress.kubernetes.io/router.entrypoints: websecure
    traefik.ingress.kubernetes.io/router.tls: "true"
    traefik.ingress.kubernetes.io/router.tls.certresolver: letsencrypt
  labels:
    saasphere.io/tenant: "{{SLUG}}"
    saasphere.io/managed-by: leia
spec:
  ingressClassName: traefik
  tls:
    - hosts: ["{{HOST}}"]
  rules:
    - host: {{HOST}}
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: {{SLUG}}-{{COMPONENT}}
                port:
                  number: 80
EOF
```

---

## 🧪 Fase 7 — Despliegue end-to-end de `cliente-demo`

Valida la pipeline completa: plantilla de namespace → plantilla de app → registry → Ingress → certificado Let's Encrypt.

> [!warning] Pre-requisito DNS Antes de este paso, crear un registro `A` en tu DNS público: `demo.tudominio.com → <IP pública fija>`. Propagar antes de lanzar el Ingress o Let's Encrypt fallará el challenge.

```bash
# 1) Crear namespace con la plantilla
/opt/k3s/templates/new-tenant.sh demo 1 2Gi 5

kubectl get ns cliente-demo --show-labels
kubectl -n cliente-demo get resourcequota,limitrange,networkpolicy

# 2) Instanciar la app (sustituye DOMAIN por tu dominio)
DOMAIN="demo.tudominio.com"
sed -e "s/{{SLUG}}/demo/g" \
    -e "s/{{COMPONENT}}/web/g" \
    -e "s#{{IMAGE}}#matrix:5000/demo-web:v1#g" \
    -e "s/{{HOST}}/${DOMAIN}/g" \
    -e "s/{{PORT}}/80/g" \
    -e "s/{{STORAGE}}/500Mi/g" \
    /opt/k3s/templates/cliente-app.yaml \
  | kubectl apply -f -

# 3) Seguir el despliegue
kubectl -n cliente-demo get pods -w
# cuando el pod pase a Running, CTRL+C

kubectl -n cliente-demo get deploy,svc,ingress,pvc
```

**Verificación del certificado Let's Encrypt**

```bash
# Ver el log de Traefik durante la emisión
kubectl -n kube-system logs -l app.kubernetes.io/name=traefik --tail=100 \
  | grep -i "acme\|letsencrypt\|demo.tudominio.com"

# Desde fuera (o con curl -k si no hay DNS aún)
curl -v https://${DOMAIN}/ 2>&1 | grep -E "subject:|issuer:"
# issuer: CN=R3, O=Let's Encrypt, C=US   ← correcto
```

> [!success] Criterio de éxito `https://demo.tudominio.com` responde con HTML de nginx, certificado emitido por Let's Encrypt, y `kubectl -n cliente-demo get all` muestra todo `Running`.

**Limpieza opcional al terminar las pruebas:**

```bash
kubectl delete namespace cliente-demo
# Borra Deployment, Service, Ingress, PVC, Quota, LimitRange y NetworkPolicies
```

---

## 🔐 Fase 8 — Validación del RBAC de LeIA

Probar el token emitido en `k3s_matrix.md` contra la API, simulando lo que hará OpenClaw. Sustituye `TOKEN` por el valor generado con `kubectl -n saasphere-system create token leia-agent`.

```bash
TOKEN="eyJhbGciOi..."   # token de leia-agent
API="https://matrix:6443"

# Debe permitir: listar namespaces
kubectl --server="${API}" --token="${TOKEN}" --insecure-skip-tls-verify \
  get namespaces

# Debe permitir: crear namespace cliente-prueba
kubectl --server="${API}" --token="${TOKEN}" --insecure-skip-tls-verify \
  create namespace cliente-prueba

# Debe permitir: borrar namespace cliente-prueba
kubectl --server="${API}" --token="${TOKEN}" --insecure-skip-tls-verify \
  delete namespace cliente-prueba

# Debe DENEGAR: borrar kube-system
kubectl --server="${API}" --token="${TOKEN}" --insecure-skip-tls-verify \
  delete namespace kube-system
# Error esperado: Forbidden
```

> [!note] Revisión del ClusterRole El `leia-role` de `k3s_matrix.md` concede `delete` sobre `namespaces`, lo cual **permitiría a LeIA borrar `kube-system`** si el nombre llega al verbo. En la prueba de arriba, Kubernetes sí acepta la petición a nivel RBAC. Mitigar con un `ValidatingAdmissionPolicy` o endureciendo el rol en una segunda iteración (separar `namespaces` con `resourceNames` permitidos).

---

## 📊 Fase 9 — Métricas del clúster hacia Sauron

Desplegar `kube-state-metrics` en `saasphere-system` para que Prometheus (en Sauron) tenga visibilidad del estado del clúster.

```bash
# Manifest oficial (versión estable)
kubectl apply -f https://raw.githubusercontent.com/kubernetes/kube-state-metrics/main/examples/standard/cluster-role-binding.yaml
kubectl apply -f https://raw.githubusercontent.com/kubernetes/kube-state-metrics/main/examples/standard/cluster-role.yaml
kubectl apply -f https://raw.githubusercontent.com/kubernetes/kube-state-metrics/main/examples/standard/service-account.yaml
kubectl apply -f https://raw.githubusercontent.com/kubernetes/kube-state-metrics/main/examples/standard/deployment.yaml
kubectl apply -f https://raw.githubusercontent.com/kubernetes/kube-state-metrics/main/examples/standard/service.yaml
```

> [!warning] Revisar namespace antes de aplicar Los manifiestos oficiales usan `namespace: kube-system`. Si prefieres mantenerlos en `saasphere-system`, descárgalos primero y edita el `metadata.namespace` antes de aplicar.

Exponerlo en la LAN para Prometheus (si corre fuera del clúster, que es el caso):

```bash
# Opción: NodePort (rápida y legítima en LAN confiable)
kubectl -n kube-system patch svc kube-state-metrics \
  -p '{"spec":{"type":"NodePort","ports":[{"port":8080,"nodePort":30080}]}}'

curl -s http://matrix:30080/metrics | head -20
```

Añadir a Prometheus en Sauron (`/opt/monitoring/prometheus/prometheus.yml`):

```yaml
scrape_configs:
  - job_name: 'kube-state-metrics'
    static_configs:
      - targets: ['matrix:30080']
```

```bash
# En Sauron
curl -X POST http://localhost:9090/-/reload
```

---

## ✅ Verificación final

```bash
# Clúster
kubectl get nodes
kubectl get pods -A | grep -vE 'Running|Completed'   # vacío = todo bien

# Orquestación operativa
kubectl get ns | grep -E 'saasphere-system|cliente-'
kubectl -n saasphere-system get sa,clusterrole,clusterrolebinding 2>/dev/null
kubectl get ingressclass traefik \
  -o jsonpath='{.metadata.annotations.ingressclass\.kubernetes\.io/is-default-class}'
# "true"

# Registry
curl -s http://matrix:5000/v2/_catalog

# Despliegue de prueba (si se mantiene)
curl -sI https://demo.tudominio.com | head -5

# Métricas del clúster llegando a Prometheus
curl -s http://sauron:9090/api/v1/targets | grep kube-state-metrics
```

---

## 📎 Próximos pasos

- [ ] Fijar decisión CNI (Flannel vs Cilium) — ver sección de decisión abierta
- [ ] Afinar `leia-role` para impedir acciones sobre namespaces de sistema
- [ ] Política de backup de `/var/lib/rancher/k3s/storage` (Fase HA con VPS)
- [ ] Replicación del Registry v2 (al tener un segundo server node)
- [ ] Integrar Promtail en Matrix → Loki en Sauron (logs de kubelet + containerd)
- [ ] Dashboard de Grafana "SaaSphere Cluster Overview" (usa kube-state-metrics)
- [ ] Primer cliente real desplegado por LeIA vía OpenClaw

---

## ⚠️ Problemas encontrados

|Problema|Causa|Solución|
|---|---|---|
|_(rellenar durante la implementación)_|||

---

_#saasphere #matrix #k3s #orquestacion #traefik #registry #rbac #networkpolicy #cilium #tfg_
## 🗺️ Contexto

| Parámetro  | Valor                                                   |
| ---------- | ------------------------------------------------------- |
| Proyecto   | SaaSphere — TFG ASIR                                    |
| Base       | Plantilla Debian Trixie ya aplicada en todas las VMs    |
| Red LAN    | `192.168.1.0/24`                                        |
| Red VPN    | `10.10.0.0/24`                                          |
| IP pública | Fija                                                    |
| Dominio    | Propio (configurar DNS A record apuntando a IP pública) |

> [!info] Estado de partida Heimdall ya está operativo con WireGuard, node_exporter, fail2ban y UFW. Las VMs Matrix, Sauron y Fallback tienen la plantilla base Debian Trixie aplicada pero sin servicios específicos todavía.

---

## 🧠 Decisiones de diseño tomadas

> [!note] Decisión: K3s + containerd, no Docker como CRI A partir de K3s v1.24 Docker no es el runtime del clúster. K3s usa su propio containerd interno. Docker se instala en Matrix únicamente como herramienta de apoyo y para el Registry privado. Los workloads de cliente van siempre por K3s/containerd.

> [!note] Decisión: Traefik como ingress, Nginx dentro de cada contenedor de cliente Traefik viene por defecto en K3s y se autoconfigura leyendo los recursos `Ingress` del clúster. Cuando LeIA despliega un cliente nuevo, Traefik detecta el Ingress y enruta el tráfico automáticamente, sin editar ningún archivo de configuración. El Nginx que sirve la web de cada cliente corre dentro de su propio contenedor.

> [!note] Decisión: Sauron fuera del clúster K3s Si Sauron corriese dentro de K3s y Matrix cayera, perderíamos la monitorización justo cuando más la necesitamos. Sauron corre como Docker standalone independiente.

> [!note] Decisión: un namespace por cliente en K3s Aislamiento de recursos, límites de CPU/RAM por cliente, y limpieza total al eliminar un cliente borrando su namespace. Es el patrón profesional estándar.

> [!note] Decisión: Fallback como agente K3s con taints Fallback se une al clúster K3s como agente pero con un taint que impide que K3s le asigne workloads de forma automática. Solo LeIA puede activarlo explícitamente en emergencia, levantando los servicios críticos por orden de prioridad.

> [!note] Decisión: LeIA interactúa con K3s vía ServiceAccount RBAC LeIA nunca accede al socket Docker directamente. Opera sobre la API de K3s con un ServiceAccount de permisos limitados: puede aplicar y eliminar recursos en namespaces de cliente, pero no puede tocar namespaces de sistema ni escalar privilegios.

---

## 📋 Orden de implementación

```
1. Sauron     → Docker + stack de monitorización (tener métricas desde el inicio)
2. Matrix     → Docker + K3s + CoreDNS + Registry v2 + Traefik (ya incluido en K3s)
3. Fallback   → Docker + K3s agent + taints
4. K3s RBAC  → ServiceAccount para LeIA
```

> [!warning] No instalar K3s en Fallback antes que en Matrix Matrix debe ser el server node. Fallback se une como agent node después. El orden es estricto.

---

# 🖥️ FASE 1 — Sauron

## 📦 Instalación de Docker

```bash
apt install -y docker.io docker-compose-plugin
systemctl enable docker
systemctl start docker
```

> [!tip] docker-compose-plugin vs docker-compose Usamos el plugin moderno (`docker compose` sin guion). Es el estándar actual y viene mantenido por Docker Inc. El binario `docker-compose` (v1) está en modo mantenimiento.

---

## ⚙️ Estructura de directorios

```bash
mkdir -p /opt/monitoring/{prometheus,grafana,loki,promtail,blackbox}
cd /opt/monitoring
```

---

## ⚙️ docker-compose.yml

```yaml
version: "3.8"

networks:
  monitoring:
    driver: bridge

volumes:
  prometheus_data:
  grafana_data:
  loki_data:

services:

  prometheus:
    image: prom/prometheus:latest
    container_name: prometheus
    restart: unless-stopped
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--storage.tsdb.retention.time=30d'
      - '--web.enable-lifecycle'
    networks:
      - monitoring

  grafana:
    image: grafana/grafana:latest
    container_name: grafana
    restart: unless-stopped
    ports:
      - "3000:3000"
    volumes:
      - grafana_data:/var/lib/grafana
    environment:
      - GF_SECURITY_ADMIN_USER=admin
      - GF_SECURITY_ADMIN_PASSWORD=saasphere2026
      - GF_METRICS_ENABLED=true
    networks:
      - monitoring

  loki:
    image: grafana/loki:latest
    container_name: loki
    restart: unless-stopped
    ports:
      - "3100:3100"
    volumes:
      - ./loki/loki-config.yml:/etc/loki/loki-config.yml:ro
      - loki_data:/loki
    command: -config.file=/etc/loki/loki-config.yml
    networks:
      - monitoring

  promtail:
    image: grafana/promtail:latest
    container_name: promtail
    restart: unless-stopped
    volumes:
      - /var/log:/var/log:ro
      - ./promtail/promtail-config.yml:/etc/promtail/config.yml:ro
    command: -config.file=/etc/promtail/config.yml
    networks:
      - monitoring

  blackbox-exporter:
    image: prom/blackbox-exporter:latest
    container_name: blackbox-exporter
    restart: unless-stopped
    ports:
      - "9115:9115"
    volumes:
      - ./blackbox/blackbox.yml:/config/blackbox.yml:ro
    command: --config.file=/config/blackbox.yml
    networks:
      - monitoring

  vmware-exporter:
    image: pryorda/vmware_exporter:latest
    container_name: vmware-exporter
    restart: unless-stopped
    ports:
      - "9272:9272"
    environment:
      - VSPHERE_HOST=192.168.1.X        # IP del ESXi
      - VSPHERE_USER=root
      - VSPHERE_PASSWORD=CAMBIAR
      - VSPHERE_IGNORE_SSL=True
    networks:
      - monitoring
```

---

## ⚙️ prometheus/prometheus.yml

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:

  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']

  - job_name: 'grafana'
    static_configs:
      - targets: ['grafana:3000']

  - job_name: 'loki'
    static_configs:
      - targets: ['loki:3100']

  - job_name: 'node'
    static_configs:
      - targets:
          - 'matrix:9100'
          - 'heimdall:9100'
          - 'leia:9100'
          - 'fallback:9100'
          - 'sauron:9100'

  - job_name: 'nginx'
    static_configs:
      - targets: ['matrix:9113']

  - job_name: 'kube-state-metrics'
    static_configs:
      - targets: ['matrix:8080']

  - job_name: 'ollama'
    static_configs:
      - targets: ['leia:8000']

  - job_name: 'nvidia-gpu'
    static_configs:
      - targets: ['leia:9400']

  - job_name: 'vmware-esxi'
    static_configs:
      - targets: ['localhost:9272']

  - job_name: 'fail2ban'
    static_configs:
      - targets:
          - 'matrix:9191'
          - 'heimdall:9100'    # textfile collector, ya integrado en Heimdall

  - job_name: 'blackbox_http'
    metrics_path: /probe
    params:
      module: [http_2xx]
    static_configs:
      - targets: []            # se añaden dominios de clientes aquí
    relabel_configs:
      - source_labels: [__address__]
        target_label: __param_target
      - source_labels: [__param_target]
        target_label: instance
      - target_label: __address__
        replacement: blackbox-exporter:9115

  - job_name: 'blackbox_icmp'
    metrics_path: /probe
    params:
      module: [icmp_ping]
    static_configs:
      - targets:
          - matrix
          - heimdall
          - leia
          - fallback
    relabel_configs:
      - source_labels: [__address__]
        target_label: __param_target
      - source_labels: [__param_target]
        target_label: instance
      - target_label: __address__
        replacement: blackbox-exporter:9115
```

---

## ⚙️ loki/loki-config.yml

```yaml
auth_enabled: false

server:
  http_listen_port: 3100

ingester:
  lifecycler:
    ring:
      kvstore:
        store: inmemory
      replication_factor: 1

schema_config:
  configs:
    - from: 2024-01-01
      store: boltdb-shipper
      object_store: filesystem
      schema: v11
      index:
        prefix: index_
        period: 24h

storage_config:
  boltdb_shipper:
    active_index_directory: /loki/index
    cache_location: /loki/cache
  filesystem:
    directory: /loki/chunks

limits_config:
  reject_old_samples: true
  reject_old_samples_max_age: 168h
```

---

## ⚙️ promtail/promtail-config.yml

```yaml
server:
  http_listen_port: 9080

positions:
  filename: /tmp/positions.yaml

clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  - job_name: sauron-logs
    static_configs:
      - targets:
          - localhost
        labels:
          job: sauron
          __path__: /var/log/*.log
```

---

## ⚙️ blackbox/blackbox.yml

```yaml
modules:
  http_2xx:
    prober: http
    timeout: 10s
    http:
      method: GET
      preferred_ip_protocol: ip4
      fail_if_not_ssl: true

  icmp_ping:
    prober: icmp
    timeout: 5s
    icmp:
      preferred_ip_protocol: ip4
```

---

## 🚀 Puesta en marcha

```bash
cd /opt/monitoring
docker compose up -d
```

---

## ⚙️ UFW — Sauron

```bash
ufw allow from 192.168.1.0/24 to any port 9090   # Prometheus
ufw allow from 192.168.1.0/24 to any port 3000   # Grafana
ufw allow from 192.168.1.0/24 to any port 3100   # Loki
ufw allow from 192.168.1.0/24 to any port 9115   # Blackbox
ufw reload
```

---

## ✅ Verificación — Sauron

```bash
docker compose ps                          # todos los contenedores Up
curl http://localhost:9090/-/healthy       # Prometheus OK
curl http://localhost:3100/ready           # Loki OK
```

Acceder a Grafana en `http://sauron:3000` y cambiar la contraseña por defecto.

---

---

# ⚡ FASE 2 — Matrix

## 📦 Instalación de Docker

```bash
apt install -y docker.io docker-compose-plugin
systemctl enable docker
systemctl start docker
```

---

## 📦 Instalación de K3s (server node)

```bash
curl -sfL https://get.k3s.io | sh -
```

> [!tip] K3s instala automáticamente
> 
> - containerd como runtime de contenedores
> - Traefik como ingress controller
> - CoreDNS interno para resolución dentro del clúster
> - kubectl configurado y listo

```bash
systemctl enable k3s
systemctl status k3s
```

Guardar el token para unir nodos agente (Fallback):

```bash
cat /var/lib/rancher/k3s/server/node-token
# Guardar este valor, lo necesita Fallback
```

---

## ⚙️ kubectl — acceso básico

```bash
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
kubectl get nodes
kubectl get pods -A
```

> [!tip] Alias recomendado
> 
> ```bash
> echo "alias k='kubectl'" >> /etc/bash.bashrc
> echo "export KUBECONFIG=/etc/rancher/k3s/k3s.yaml" >> /etc/bash.bashrc
> source /etc/bash.bashrc
> ```

---

## 📦 CoreDNS standalone — DNS interno de la LAN

> [!note] Decisión: CoreDNS standalone en Docker K3s ya incluye CoreDNS internamente para resolución dentro del clúster. Este CoreDNS adicional resuelve nombres entre las VMs de la LAN (matrix, sauron, heimdall, leia, fallback) para que los configs de Prometheus y los servicios puedan usar hostnames en lugar de IPs.

```bash
mkdir -p /opt/coredns
```

```bash
# /opt/coredns/Corefile
. {
    hosts /etc/coredns/hosts {
        192.168.1.X   matrix
        192.168.1.X   sauron
        192.168.1.X   heimdall
        192.168.1.X   leia
        192.168.1.X   fallback
        fallthrough
    }
    forward . 8.8.8.8 1.1.1.1
    log
    errors
    cache 30
}
```

> [!warning] Sustituir las IPs Completar cada IP con la dirección real asignada a cada VM en la LAN.

```bash
# /opt/coredns/docker-compose.yml
version: "3.8"
services:
  coredns:
    image: coredns/coredns:latest
    container_name: coredns
    restart: unless-stopped
    ports:
      - "53:53/udp"
      - "53:53/tcp"
    volumes:
      - ./Corefile:/etc/coredns/Corefile:ro
      - ./Corefile:/etc/coredns/hosts:ro
```

```bash
cd /opt/coredns
docker compose up -d
```

Apuntar todas las VMs a Matrix como DNS:

```bash
# En cada VM: /etc/resolv.conf
nameserver 192.168.1.X   # IP de Matrix
```

---

## 📦 Docker Registry v2 — Registro privado de imágenes

```bash
mkdir -p /opt/registry
```

```yaml
# /opt/registry/docker-compose.yml
version: "3.8"
services:
  registry:
    image: registry:2
    container_name: registry
    restart: unless-stopped
    ports:
      - "5000:5000"
    volumes:
      - /opt/registry/data:/var/lib/registry
    environment:
      REGISTRY_STORAGE_DELETE_ENABLED: "true"
```

```bash
cd /opt/registry
docker compose up -d
```

Configurar K3s para que confíe en el registro local (sin TLS en LAN):

```bash
mkdir -p /etc/rancher/k3s
cat > /etc/rancher/k3s/registries.yaml << EOF
mirrors:
  "matrix:5000":
    endpoint:
      - "http://matrix:5000"
EOF

systemctl restart k3s
```

> [!tip] Uso del registro
> 
> ```bash
> # Subir una imagen al registro privado
> docker tag nginx:alpine matrix:5000/cliente1-web:v1
> docker push matrix:5000/cliente1-web:v1
> 
> # Referenciar en manifiestos K3s
> image: matrix:5000/cliente1-web:v1
> ```

---

## ⚙️ Traefik — configuración SSL con Let's Encrypt

Traefik ya corre dentro de K3s. Hay que configurarle el proveedor ACME para SSL automático.

```bash
mkdir -p /var/lib/rancher/k3s/server/manifests
```

```yaml
# /var/lib/rancher/k3s/server/manifests/traefik-config.yaml
apiVersion: helm.cattle.io/v1
kind: HelmChartConfig
metadata:
  name: traefik
  namespace: kube-system
spec:
  valuesContent: |-
    additionalArguments:
      - "--certificatesresolvers.letsencrypt.acme.email=TU_EMAIL@dominio.com"
      - "--certificatesresolvers.letsencrypt.acme.storage=/data/acme.json"
      - "--certificatesresolvers.letsencrypt.acme.tlschallenge=true"
    persistence:
      enabled: true
      size: 128Mi
    ports:
      websecure:
        tls:
          enabled: true
```

> [!warning] Sustituir el email Let's Encrypt lo usa para notificaciones de expiración de certificados.

---

## ⚙️ Estructura de namespaces base

```bash
# Namespace de infraestructura interna (no clientes)
kubectl create namespace saasphere-system

# Los namespaces de clientes se crean dinámicamente por LeIA:
# kubectl create namespace cliente-NOMBRE
```

---

## 🔐 ServiceAccount RBAC para LeIA

```yaml
# /opt/k3s/leia-rbac.yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: leia-agent
  namespace: saasphere-system

---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: leia-role
rules:
  - apiGroups: ["", "apps", "networking.k8s.io"]
    resources: ["namespaces", "deployments", "services", "ingresses", "pods", "configmaps"]
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]

---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: leia-rolebinding
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: leia-role
subjects:
  - kind: ServiceAccount
    name: leia-agent
    namespace: saasphere-system
```

```bash
kubectl apply -f /opt/k3s/leia-rbac.yaml
```

Extraer el token para LeIA:

```bash
kubectl -n saasphere-system create token leia-agent --duration=8760h
# Guardar este token en la configuración de OpenClaw
```

> [!danger] Este token es la llave de LeIA al clúster No incluirlo en repositorios git ni en logs. Guardarlo en la configuración de OpenClaw como variable de entorno o secreto cifrado.

---

## ⚙️ UFW — Matrix

```bash
ufw allow from 192.168.1.0/24 to any port 6443   # K3s API (para LeIA y kubectl remoto)
ufw allow from 192.168.1.0/24 to any port 5000   # Registry privado
ufw allow from 192.168.1.0/24 to any port 53     # CoreDNS
ufw allow 80/tcp                                  # Traefik HTTP
ufw allow 443/tcp                                 # Traefik HTTPS
ufw allow from 192.168.1.0/24 to any port 9100   # node_exporter
ufw allow from 192.168.1.0/24 to any port 9113   # nginx-exporter (si aplica)
ufw allow from 192.168.1.0/24 to any port 8080   # kube-state-metrics
ufw reload
```

---

## ✅ Verificación — Matrix

```bash
kubectl get nodes                          # Matrix aparece como Ready
kubectl get pods -n kube-system            # Traefik, CoreDNS internos corriendo
docker ps                                  # coredns y registry corriendo
curl http://localhost:5000/v2/_catalog     # Registry responde: {"repositories":[]}
```

---

---

# 💾 FASE 3 — Fallback

## 📦 Instalación de Docker

```bash
apt install -y docker.io docker-compose-plugin
systemctl enable docker
systemctl start docker
```

---

## 📦 Unirse al clúster K3s como agente

```bash
# TOKEN obtenido de Matrix en la Fase 2
K3S_TOKEN="TOKEN_DEL_SERVIDOR"
K3S_URL="https://192.168.1.X:6443"   # IP de Matrix

curl -sfL https://get.k3s.io | K3S_URL=$K3S_URL K3S_TOKEN=$K3S_TOKEN sh -s - agent
```

```bash
systemctl enable k3s-agent
systemctl status k3s-agent
```

Verificar desde Matrix que Fallback se ha unido:

```bash
kubectl get nodes
# Debe aparecer fallback como Ready
```

---

## ⚙️ Taint — impedir workloads automáticos en Fallback

```bash
kubectl taint nodes fallback saasphere/role=fallback:NoSchedule
```

> [!note] Qué hace este taint K3s no asignará ningún pod a Fallback a menos que el manifiesto incluya explícitamente una `toleration` para este taint. Solo LeIA aplicará esa toleración cuando active el modo de emergencia.

Verificar el taint:

```bash
kubectl describe node fallback | grep Taint
# Taints: saasphere/role=fallback:NoSchedule
```

---

## ⚙️ UFW — Fallback

```bash
ufw allow from 192.168.1.0/24 to any port 9100   # node_exporter
ufw allow from 192.168.1.X to any port 10250      # kubelet (solo desde Matrix)
ufw reload
```

---

## ✅ Verificación — Fallback

```bash
# Desde Matrix
kubectl get nodes
# NAME       STATUS   ROLES                  AGE
# matrix     Ready    control-plane,master   Xm
# fallback   Ready    <none>                 Xm

kubectl describe node fallback | grep Taint
# Taints: saasphere/role=fallback:NoSchedule
```

---

---

## 📊 Estado final de la infraestructura

|Nodo|Servicios activos|Runtime|
|---|---|---|
|**Heimdall**|WireGuard, node_exporter, fail2ban|Systemd|
|**Sauron**|Prometheus, Grafana, Loki, Promtail, Blackbox, VMware exporter|Docker standalone|
|**Matrix**|K3s (server), Traefik, CoreDNS LAN, Registry v2, node_exporter|K3s + Docker|
|**Fallback**|K3s (agent, taint NoSchedule), node_exporter|K3s|
|**LeIA**|Ollama, OpenClaw _(pendiente)_|Systemd / Docker|

---

## 📎 Próximos pasos

- [ ] Completar IPs reales en el Corefile de CoreDNS
- [ ] Configurar `/etc/resolv.conf` en todas las VMs apuntando a Matrix
- [ ] Sustituir email en configuración de Traefik + Let's Encrypt
- [ ] Guardar el token de leia-agent en la configuración de OpenClaw
- [ ] Desplegar kube-state-metrics en K3s para métricas del clúster
- [ ] Configurar Promtail en Matrix y Fallback para enviar logs a Loki
- [ ] Primer despliegue de prueba de un contenedor cliente con Ingress

---

## ⚠️ Problemas encontrados

| Problema                                | Causa | Solución |
| --------------------------------------- | ----- | -------- |
| _(completar durante la implementación)_ |       |          |

---

_#saasphere #matrix #sauron #fallback #k3s #docker #traefik #coredns #registry #prometheus #leia #rbac_
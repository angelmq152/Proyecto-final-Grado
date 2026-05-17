## 🗺️ Contexto

|Parámetro|Valor|
|---|---|
|Nodo|Matrix (VM en ESXi)|
|SO|Debian Trixie (minimal)|
|IP local|`192.168.1.202`|
|RAM|5,5 GB / vCPU x3 / Disco 500 GB|
|Rol|K3s server, Traefik, Registry v2 privado|
|Red LAN|`192.168.1.0/24`|

> [!info] Estado de partida Plantilla base Debian Trixie ya aplicada: UFW activo, fail2ban, SSH sin root, node_exporter en `:9100`, unattended-upgrades y auditd.

> [!note] Decisiones de diseño
> 
> - **K3s usa containerd** como CRI nativo. Docker se instala solo como herramienta auxiliar y para el Registry.
> - **Traefik** viene incluido en K3s y actúa como ingress controller. Los dominios de cliente los resuelve el DNS público de internet — Traefik enruta por header `Host`, no necesita DNS interno.
> - **Resolución de hostnames LAN** mediante `/etc/hosts` en cada nodo. CoreDNS descartado por ser over-engineering para 5 nodos fijos con IPs estáticas.
> - **Sauron corre fuera del clúster K3s** (Docker standalone) para no perder monitorización si Matrix cae.

---

## 🗺️ IPs de la infraestructura

|Nodo|IP|
|---|---|
|LeIA|`192.168.1.200`|
|Sauron|`192.168.1.201`|
|Matrix|`192.168.1.202`|
|Heimdall|`192.168.1.203`|
|Fallback|`192.168.1.210`|
|ESXi|`192.168.1.99`|

---

## 📦 1. Docker

> [!note] Docker en Matrix no orquesta workloads de cliente — eso es K3s/containerd. Docker se usa únicamente para el Registry v2 privado.

Los repos oficiales de Docker no tienen paquetes para Debian Trixie. Se fuerza el repositorio de Bookworm, que funciona perfectamente en Trixie.

```bash
apt install -y ca-certificates curl gnupg

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/debian bookworm stable" | \
  tee /etc/apt/sources.list.d/docker.list > /dev/null

apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

systemctl enable docker
systemctl start docker
docker --version
```

---

## 📦 2. K3s — Server node

```bash
curl -sfL https://get.k3s.io | sh -
systemctl enable k3s
systemctl status k3s
```

> [!tip] K3s instala automáticamente
> 
> - `containerd` como runtime de contenedores
> - `Traefik` como ingress controller
> - `CoreDNS` interno para resolución dentro del clúster
> - `kubectl` configurado y listo

Guardar el token para unir Fallback más adelante:

```bash
cat /var/lib/rancher/k3s/server/node-token
```

> [!danger] Guardar este token Es la credencial que necesita Fallback para unirse al clúster. Guardarlo en un lugar seguro.

---

## ⚙️ 3. kubectl + alias

```bash
echo "export KUBECONFIG=/etc/rancher/k3s/k3s.yaml" >> /etc/bash.bashrc
echo "alias k='kubectl'" >> /etc/bash.bashrc
source /etc/bash.bashrc

kubectl get nodes
kubectl get pods -A
```

---

## ⚙️ 4. Resolución de hostnames LAN — /etc/hosts

> [!note] Decisión: /etc/hosts frente a CoreDNS Para 5 nodos con IPs estáticas, `/etc/hosts` cubre la necesidad sin añadir complejidad. CoreDNS aportaría valor con infraestructura dinámica o decenas de nodos. Aquí es over-engineering.

```bash
echo "nameserver 8.8.8.8" > /etc/resolv.conf

cat >> /etc/hosts << 'EOF'
192.168.1.200   leia
192.168.1.201   sauron
192.168.1.202   matrix
192.168.1.203   heimdall
192.168.1.210   fallback
EOF

ping -c 2 sauron
ping -c 2 google.com
```

> [!tip] Replicar en el resto de nodos Añadir el mismo bloque a `/etc/hosts` en Sauron, Heimdall, LeIA y Fallback.

---

## 📦 5. Registry v2 — Registro privado de imágenes

> [!note] Por qué un Registry privado LeIA genera y despliega imágenes de cliente. K3s necesita tirar de esas imágenes desde la LAN sin depender de Docker Hub.

```bash
mkdir -p /opt/registry/data

cat > /opt/registry/docker-compose.yml << 'EOF'
services:
  registry:
    image: registry:2
    container_name: registry
    restart: unless-stopped
    ports:
      - "5000:5000"
    volumes:
      - ./data:/var/lib/registry
    environment:
      REGISTRY_STORAGE_DELETE_ENABLED: "true"
EOF

cd /opt/registry && docker compose up -d
curl http://localhost:5000/v2/_catalog
# Respuesta esperada: {"repositories":[]}
```

Configurar K3s para confiar en el registry local sin TLS:

```bash
mkdir -p /etc/rancher/k3s
cat > /etc/rancher/k3s/registries.yaml << 'EOF'
mirrors:
  "matrix:5000":
    endpoint:
      - "http://matrix:5000"
EOF

systemctl restart k3s
kubectl get nodes
```

> [!tip] Uso del registry en el día a día
> 
> ```bash
> docker tag nginx:alpine matrix:5000/cliente1-web:v1
> docker push matrix:5000/cliente1-web:v1
> # En manifiestos K3s:
> # image: matrix:5000/cliente1-web:v1
> ```

---

## ⚙️ 6. Traefik — SSL automático con Let's Encrypt

K3s recoge automáticamente los manifiestos de `/var/lib/rancher/k3s/server/manifests/`.

```bash
cat > /var/lib/rancher/k3s/server/manifests/traefik-config.yaml << 'EOF'
apiVersion: helm.cattle.io/v1
kind: HelmChartConfig
metadata:
  name: traefik
  namespace: kube-system
spec:
  valuesContent: |-
    additionalArguments:
      - "--certificatesresolvers.letsencrypt.acme.email=angelmq152@gmail.com"
      - "--certificatesresolvers.letsencrypt.acme.storage=/data/acme.json"
      - "--certificatesresolvers.letsencrypt.acme.tlschallenge=true"
    persistence:
      enabled: true
      size: 128Mi
    ports:
      websecure:
        tls:
          enabled: true
EOF
```

```bash
kubectl get pods -n kube-system | grep traefik
```

> [!warning] Requisito para Let's Encrypt Los puertos 80 y 443 deben llegar a Matrix desde internet (port forwarding en el router). Let's Encrypt valida el dominio via HTTP-01 challenge en el puerto 80.

---

## ⚙️ 7. Namespaces base

```bash
kubectl create namespace saasphere-system
kubectl get namespaces
```

> [!note] Namespaces de cliente Los namespaces de cliente (`cliente-NOMBRE`) los crea LeIA dinámicamente en el momento del despliegue.

---

## 🔐 8. RBAC — ServiceAccount para LeIA

```bash
mkdir -p /opt/k3s
cat > /opt/k3s/leia-rbac.yaml << 'EOF'
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
EOF

kubectl apply -f /opt/k3s/leia-rbac.yaml
```

Generar el token de acceso para LeIA (válido 1 año):

```bash
kubectl -n saasphere-system create token leia-agent --duration=8760h
```

> [!danger] Seguridad del token Este token es la llave de LeIA al clúster K3s. Guardarlo como secreto cifrado en la configuración de OpenClaw. Nunca en un repositorio git ni en logs.

---

## 🔥 9. UFW

```bash
ufw allow from 192.168.1.0/24 to any port 6443      # K3s API (LeIA + kubectl remoto)
ufw allow from 192.168.1.0/24 to any port 5000      # Registry privado
ufw allow 80/tcp                                     # Traefik HTTP
ufw allow 443/tcp                                    # Traefik HTTPS
ufw allow from 192.168.1.0/24 to any port 8080      # kube-state-metrics
ufw allow from 192.168.1.0/24 to any port 10250     # kubelet
ufw allow from 192.168.1.0/24 to any port 9100      # node_exporter
ufw allow proto udp from 192.168.1.0/24 to any port 8472  # Flannel overlay network
ufw reload
ufw status
```

---

## ✅ Verificación final

```bash
kubectl get nodes                        # Matrix: Ready
kubectl get pods -A                      # Traefik, CoreDNS, metrics-server: Running
docker ps                                # registry: Up
curl http://localhost:5000/v2/_catalog   # {"repositories":[]}
ping -c 2 sauron                         # resuelve 192.168.1.201
ping -c 2 google.com                     # forwarding DNS funciona
```

---

## ⚠️ Problemas encontrados

|Problema|Causa|Solución|
|---|---|---|
|`docker.io` no encontrado en Trixie|Debian Trixie no tiene paquetes Docker en sus repos|Añadir repo oficial de Docker forzando Bookworm|
|`Temporary failure resolving` en apt|Matrix sin DNS configurado al inicio|Añadir `nameserver 8.8.8.8` en `/etc/resolv.conf`|
|`mkdir` antes del `cat` en leia-rbac|Orden incorrecta en los comandos|Crear el directorio antes de escribir el archivo|
|`ufw allow 8472/udp` devuelve error|UFW no acepta el protocolo en ese formato|Usar `ufw allow proto udp ... port 8472`|

---

_#saasphere #matrix #k3s #traefik #docker #registry #rbac #leia #tfg_
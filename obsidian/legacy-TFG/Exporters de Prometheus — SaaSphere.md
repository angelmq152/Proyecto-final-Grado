## 🗺️ Contexto

|Parámetro|Valor|
|---|---|
|Proyecto|SaaSphere — TFG ASIR|
|Stack de monitorización|Prometheus + Grafana + Loki (Sauron)|
|Nodos físicos|LeIA, ESXi, Fallback|
|Objetivo|Identificar todos los exporters necesarios para cubrir cada servicio|

> [!info] Criterio de selección Se han priorizado exporters oficiales, ligeros y compatibles con Docker/K3s. Para cada servicio se indica si expone métricas de forma nativa o necesita un exporter externo.

---

## 📊 Inventario de servicios y exporters

|#|Servicio|Nodo|Métricas nativas|Exporter necesario|Puerto por defecto|
|---|---|---|---|---|---|
|1|**Sistema operativo (Linux)**|Todos|No|`node_exporter`|`:9100`|
|2|**Nginx** (proxy inverso)|Matrix|Sí (`stub_status`)|`nginx-prometheus-exporter`|`:9113`|
|3|**WireGuard** (VPN)|Heimdall|No|`prometheus_wireguard_exporter`|`:9586`|
|4|**K3s / Kubernetes**|Matrix|Sí (API server, kubelet)|`kube-state-metrics`|`:8080`|
|5|**Docker / contenedores**|Matrix|No|`cAdvisor`|`:8080`|
|6|**Prometheus**|Sauron|Sí (self-monitoring)|Ninguno|`:9090/metrics`|
|7|**Grafana**|Sauron|Sí|Ninguno|`:3000/metrics`|
|8|**Loki**|Sauron|Sí|Ninguno|`:3100/metrics`|
|9|**Ollama** (IA/LLM)|LeIA|No|`ollama-exporter`|`:8000`|
|10|**VMware ESXi**|ESXi (hipervisor)|No|`vmware_exporter`|`:9272`|
|11|**NVIDIA GPU** (RTX 3060 Ti)|LeIA|No|`dcgm-exporter`|`:9400`|
|12|**Fail2ban**|Todos (expuestos)|No|`fail2ban-prometheus-exporter`|`:9191`|
|13|**Webs de clientes / SSL**|Sauron (probe)|N/A|`blackbox_exporter`|`:9115`|

---

## 📦 Detalle de cada exporter

### 1. Node Exporter

|Parámetro|Valor|
|---|---|
|Repo|`prometheus/node_exporter`|
|Despliegue|Binario o contenedor en cada nodo|
|Puerto|`:9100/metrics`|

**Métricas clave:** CPU, RAM, disco, red, temperatura, carga del sistema.

> [!tip] Despliegue recomendado Instalar como servicio systemd en cada nodo (Heimdall, Matrix, Fallback, LeIA). En K3s se puede desplegar como DaemonSet para cubrir todos los nodos automáticamente.

---

### 2. Nginx Prometheus Exporter

|Parámetro|Valor|
|---|---|
|Repo|`nginx/nginx-prometheus-exporter`|
|Requisito previo|Habilitar `stub_status` en Nginx|
|Puerto|`:9113/metrics`|

**Métricas clave:** conexiones activas, peticiones por segundo, conexiones aceptadas/rechazadas, estado de los upstreams.

```nginx
# Añadir en nginx.conf para habilitar stub_status
server {
    listen 8081;
    location /stub_status {
        stub_status;
        allow 127.0.0.1;
        deny all;
    }
}
```

```bash
# Ejecución del exporter
docker run -p 9113:9113 nginx/nginx-prometheus-exporter \
  --nginx.scrape-uri=http://matrix:8081/stub_status
```

---

### 3. WireGuard Exporter

|Parámetro|Valor|
|---|---|
|Repo|`MindFlavor/prometheus_wireguard_exporter`|
|Alternativa ligera|Script bash + node_exporter textfile collector|
|Puerto|`:9586/metrics`|

**Métricas clave:** bytes enviados/recibidos por peer, último handshake, estado del túnel.

> [!warning] Permisos El exporter necesita acceso a `wg show` que requiere permisos root o `CAP_NET_ADMIN`.

```bash
docker run -d --cap-add NET_ADMIN --network host \
  -v /var/run/wireguard:/var/run/wireguard \
  -p 9586:9586 \
  mindflavor/prometheus-wireguard-exporter
```

---

### 4. Kube-State-Metrics

|Parámetro|Valor|
|---|---|
|Repo|`kubernetes/kube-state-metrics`|
|Despliegue|Deployment dentro de K3s|
|Puerto|`:8080/metrics`|

**Métricas clave:** estado de pods, deployments, nodos, réplicas deseadas vs actuales, jobs, CronJobs.

> [!note] Complemento a las métricas nativas de K3s K3s ya expone métricas del API server (`/metrics`) y del kubelet (`/metrics/cadvisor`). kube-state-metrics añade el estado lógico de los objetos de Kubernetes, no el consumo de recursos.

```bash
kubectl apply -f https://github.com/kubernetes/kube-state-metrics/tree/main/examples/standard
```

---

### 5. cAdvisor (Container Advisor)

|Parámetro|Valor|
|---|---|
|Repo|`google/cadvisor`|
|Despliegue|Contenedor con acceso a `/var/run/docker.sock`|
|Puerto|`:8080/metrics`|

**Métricas clave:** CPU, memoria, red y disco por contenedor individual.

> [!info] En K3s El kubelet ya integra métricas de cAdvisor en `/metrics/cadvisor`. Solo es necesario desplegarlo de forma independiente si necesitas métricas más detalladas o si monitorizas contenedores Docker fuera de K3s.

---

### 6. Prometheus (self-monitoring)

|Parámetro|Valor|
|---|---|
|Endpoint|`:9090/metrics` (nativo)|
|Configuración|Añadir un `scrape_config` apuntando a sí mismo|

**Métricas clave:** muestras ingestadas, duración de queries, targets activos/caídos, almacenamiento en disco.

```yaml
scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']
```

---

### 7. Grafana (self-monitoring)

|Parámetro|Valor|
|---|---|
|Endpoint|`:3000/metrics` (nativo)|
|Requisito|Habilitar en `grafana.ini` → `[metrics] enabled = true`|

**Métricas clave:** dashboards cargados, alertas activas, latencia de datasources, sesiones de usuario.

---

### 8. Loki (self-monitoring)

|Parámetro|Valor|
|---|---|
|Endpoint|`:3100/metrics` (nativo)|

**Métricas clave:** logs ingestados por segundo, chunks almacenados, latencia de queries, errores de ingesta.

---

### 9. Ollama Exporter

|Parámetro|Valor|
|---|---|
|Repo|`frcooper/ollama-exporter`|
|Alternativa|`NorskHelsenett/ollama-metrics`|
|Puerto|`:8000/metrics`|

**Métricas clave:** modelos cargados en RAM, VRAM consumida por modelo, tokens de prompt/respuesta, duración de inferencias, estado de salud de la API.

> [!warning] Ollama no expone `/metrics` nativo Ollama no tiene un endpoint Prometheus integrado. Es obligatorio usar un exporter externo que actúe como proxy transparente entre la aplicación y Ollama.

```bash
docker run -d --name ollama-exporter -p 8000:8000 \
  -e OLLAMA_HOST="http://leia:11434" \
  frcooper/ollama-exporter
```

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'ollama'
    static_configs:
      - targets: ['leia:8000']
```

---

### 10. VMware Exporter (ESXi)

|Parámetro|Valor|
|---|---|
|Repo|`pryorda/vmware_exporter`|
|Alternativa standalone|`sylweltan/prometheus-vmware-exporter` (puerto `:9512`)|
|Puerto|`:9272/metrics`|

**Métricas clave:** CPU/RAM del host ESXi, estado de las VMs, uso de datastores, snapshots activos, rendimiento de red del hipervisor.

```bash
docker run -d --name vmware-exporter -p 9272:9272 \
  -e VSPHERE_HOST=192.168.1.X \
  -e VSPHERE_USER=root \
  -e VSPHERE_PASSWORD=password \
  -e VSPHERE_IGNORE_SSL=True \
  pryorda/vmware_exporter
```

> [!note] Sin vCenter Al usar ESXi standalone (sin vCenter), se recomienda `sylweltan/prometheus-vmware-exporter` que conecta directamente al host ESXi sin necesidad de vCenter.

---

### 11. NVIDIA DCGM Exporter

|Parámetro|Valor|
|---|---|
|Repo|`NVIDIA/dcgm-exporter`|
|Requisito|NVIDIA drivers + Docker con runtime NVIDIA|
|Puerto|`:9400/metrics`|
|Dashboard Grafana|ID `12239`|

**Métricas clave:** utilización GPU (%), temperatura, frecuencia SM/MEM, uso de VRAM, consumo energético, errores ECC.

```bash
docker run -d --gpus all --cap-add SYS_ADMIN \
  --rm -p 9400:9400 \
  nvcr.io/nvidia/k8s/dcgm-exporter:4.5.2-4.8.1-distroless
```

> [!tip] Imprescindible para LeIA Este nodo ejecuta Ollama con la RTX 3060 Ti. Monitorizar la GPU es crítico para detectar cuellos de botella en inferencias, sobrecalentamiento o saturación de VRAM.

---

### 12. Fail2ban Prometheus Exporter

|Parámetro|Valor|
|---|---|
|Repo|`hctrdev/fail2ban-prometheus-exporter`|
|Alternativa|`jangrewe/prometheus-fail2ban-exporter` (usa textfile collector)|
|Puerto|`:9191/metrics`|

**Métricas clave:** IPs actualmente baneadas por jail, total de baneos históricos, conexiones fallidas actuales, total de conexiones fallidas, errores de comunicación con el servidor fail2ban.

> [!warning] Permisos sobre el socket El exporter se conecta al socket Unix de fail2ban (`/var/run/fail2ban/fail2ban.sock`). Por defecto este socket pertenece a root. Es necesario ejecutar el exporter como root o ajustar los permisos del socket.

```bash
docker run -d --name fail2ban-exporter \
  -v /var/run/fail2ban:/var/run/fail2ban:ro \
  -p 9191:9191 \
  registry.gitlab.com/hctrdev/fail2ban-prometheus-exporter:latest
```

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'fail2ban'
    static_configs:
      - targets:
          - 'matrix:9191'
          - 'heimdall:9191'
```

> [!tip] Dónde desplegarlo En cada nodo que tenga fail2ban activo y esté expuesto a internet o reciba conexiones SSH. En SaaSphere como mínimo: Heimdall (VPN) y Matrix (proxy inverso).

---

### 13. Blackbox Exporter

|Parámetro|Valor|
|---|---|
|Repo|`prometheus/blackbox_exporter`|
|Despliegue|Contenedor en Sauron|
|Puerto|`:9115/probe`|
|Dashboard Grafana|ID `7587` o `5345`|

**Métricas clave:** disponibilidad del endpoint (`probe_success`), tiempo de respuesta HTTP, tiempo de resolución DNS, expiración de certificados SSL (`probe_ssl_earliest_cert_expiry`), latencia ICMP.

> [!tip] Fundamental para SaaSphere Este exporter es el que permite monitorizar las webs de los clientes desde fuera: si una web se cae, si el certificado SSL está a punto de caducar, o si hay problemas de latencia. Es lo que permite a LeIA detectar incidencias antes de que el cliente las note.

**Configuración del exporter** (`blackbox.yml`):

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

  tcp_connect:
    prober: tcp
    timeout: 5s
```

```bash
docker run -d --name blackbox-exporter \
  -p 9115:9115 \
  -v /path/to/blackbox.yml:/config/blackbox.yml \
  prom/blackbox-exporter --config.file=/config/blackbox.yml
```

**Configuración en Prometheus** (scrape de las webs de clientes):

```yaml
scrape_configs:
  # --- Probes HTTP a webs de clientes ---
  - job_name: 'blackbox_http'
    metrics_path: /probe
    params:
      module: [http_2xx]
    static_configs:
      - targets:
          - https://cliente1.saasphere.es
          - https://cliente2.saasphere.es
          - https://cliente3.saasphere.es
    relabel_configs:
      - source_labels: [__address__]
        target_label: __param_target
      - source_labels: [__param_target]
        target_label: instance
      - target_label: __address__
        replacement: sauron:9115

  # --- Probes ICMP a nodos internos ---
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
        replacement: sauron:9115
```

> [!note] Alertas recomendadas con Blackbox
> 
> - **Web caída:** `probe_success{job="blackbox_http"} == 0` durante 3 minutos → alerta crítica
> - **SSL a punto de caducar:** `(probe_ssl_earliest_cert_expiry - time()) / 86400 < 30` → alerta warning
> - **Nodo interno no responde a ping:** `probe_success{job="blackbox_icmp"} == 0` → alerta crítica

---

## ⚙️ Resumen de configuración en Prometheus

```yaml
# prometheus.yml — scrape_configs completo
scrape_configs:

  # --- Self-monitoring ---
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']

  # --- Node Exporter (todos los nodos) ---
  - job_name: 'node'
    static_configs:
      - targets:
          - 'matrix:9100'
          - 'heimdall:9100'
          - 'leia:9100'
          - 'fallback:9100'

  # --- Nginx ---
  - job_name: 'nginx'
    static_configs:
      - targets: ['matrix:9113']

  # --- WireGuard ---
  - job_name: 'wireguard'
    static_configs:
      - targets: ['heimdall:9586']

  # --- Kube-State-Metrics ---
  - job_name: 'kube-state-metrics'
    static_configs:
      - targets: ['matrix:8080']

  # --- Ollama ---
  - job_name: 'ollama'
    static_configs:
      - targets: ['leia:8000']

  # --- NVIDIA GPU ---
  - job_name: 'nvidia-gpu'
    static_configs:
      - targets: ['leia:9400']

  # --- VMware ESXi ---
  - job_name: 'vmware-esxi'
    static_configs:
      - targets: ['sauron:9272']

  # --- Grafana ---
  - job_name: 'grafana'
    static_configs:
      - targets: ['localhost:3000']

  # --- Loki ---
  - job_name: 'loki'
    static_configs:
      - targets: ['localhost:3100']

  # --- Fail2ban ---
  - job_name: 'fail2ban'
    static_configs:
      - targets:
          - 'matrix:9191'
          - 'heimdall:9191'

  # --- Blackbox HTTP (webs de clientes) ---
  - job_name: 'blackbox_http'
    metrics_path: /probe
    params:
      module: [http_2xx]
    static_configs:
      - targets:
          - https://cliente1.saasphere.es
          - https://cliente2.saasphere.es
    relabel_configs:
      - source_labels: [__address__]
        target_label: __param_target
      - source_labels: [__param_target]
        target_label: instance
      - target_label: __address__
        replacement: sauron:9115

  # --- Blackbox ICMP (nodos internos) ---
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
        replacement: sauron:9115
```

---

## 📎 Notas

> [!note] Decisión: exporters como contenedores Todos los exporters se desplegarán preferiblemente como contenedores Docker para mantener la coherencia con la arquitectura de SaaSphere y facilitar su gestión con K3s.

> [!tip] Dashboards de Grafana recomendados
> 
> - **Node Exporter Full:** ID `1860`
> - **Nginx:** ID `12708`
> - **K3s / kube-state-metrics:** ID `13332`
> - **NVIDIA DCGM:** ID `12239`
> - **Blackbox Exporter:** ID `7587` o `5345`
> - **VMware ESXi:** buscar en Grafana Labs "VMware ESXi"

| Exporter                      | Repo / Fuente                                               |
| ----------------------------- | ----------------------------------------------------------- |
| node_exporter                 | https://github.com/prometheus/node_exporter                 |
| nginx-prometheus-exporter     | https://github.com/nginx/nginx-prometheus-exporter          |
| prometheus_wireguard_exporter | https://github.com/MindFlavor/prometheus_wireguard_exporter |
| kube-state-metrics            | https://github.com/kubernetes/kube-state-metrics            |
| cAdvisor                      | https://github.com/google/cadvisor                          |
| ollama-exporter               | https://github.com/frcooper/ollama-exporter                 |
| vmware_exporter               | https://github.com/pryorda/vmware_exporter                  |
| dcgm-exporter                 | https://github.com/NVIDIA/dcgm-exporter                     |
| fail2ban-prometheus-exporter  | https://gitlab.com/hctrdev/fail2ban-prometheus-exporter     |
| blackbox_exporter             | https://github.com/prometheus/blackbox_exporter             |

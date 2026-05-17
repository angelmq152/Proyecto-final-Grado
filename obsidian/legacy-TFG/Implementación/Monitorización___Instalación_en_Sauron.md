# 📊 Sauron — Stack de Monitorización

## 🗺️ Contexto

| Parámetro | Valor |
|---|---|
| Nodo | Sauron (VM en ESXi) |
| SO | Debian 13 Trixie (desde plantilla base) |
| IP local | `192.168.1.201` |
| RAM / vCPU / Disco | 2 GB / 1 / 100 GB |
| Rol | Observabilidad (métricas + logs + blackbox) |
| Runtime | Docker CE + Compose v2 (fuera del clúster K3s) |
| Directorio de trabajo | `/opt/monitoring` |

> [!info] Estado de partida
> VM recién clonada de la plantilla base Debian Trixie: UFW activo, fail2ban, SSH sin root, `prometheus-node-exporter` en `:9100` (paquete Debian, `active running`), unattended-upgrades y auditd. Sin otros servicios encima.

---

## 🧠 Decisiones de diseño

> [!note] Decisión: Sauron fuera del clúster K3s
> Si Sauron corriese dentro de K3s y Matrix cayera, perderíamos la monitorización justo cuando más la necesitamos. Se mantiene como Docker standalone independiente.

> [!note] Decisión: repositorio oficial de Docker, no `docker.io` de Debian
> Consistencia entre nodos. Matrix ya usa el repositorio oficial (con Bookworm forzado sobre Trixie). Mezclar orígenes mete versiones distintas y posibles conflictos en cgroup driver.

> [!note] Decisión: versiones pineadas (no `:latest`)
> Para un proyecto "production-credible" evitar que `docker compose pull` meses después rompa el stack por un breaking change de cualquier imagen. Patrón profesional.

> [!note] Decisión: secretos fuera del compose (`.env` con `chmod 600`)
> La contraseña de Grafana y futuros tokens (Telegram, SMTP) no pueden ir hardcodeados en el YAML si algún día se sube a git.

> [!note] Decisión: retención explícita en Loki (30 días)
> Loki por defecto no borra nunca. Se configura `compactor` + `retention_period: 720h` para evitar que los logs se coman el disco.

> [!note] Decisión: provisioning de datasources y dashboards
> Datasources y dashboards definidos por archivos en `grafana/provisioning/` y `grafana/dashboards/`. Reproducible, versionable en git, nada clicado a mano.

---

## 🏗️ Arquitectura del stack

```
/opt/monitoring/
├── .env                               # Secretos (chmod 600)
├── docker-compose.yml                 # 5 servicios
├── prometheus/
│   └── prometheus.yml                 # Scrape config
├── grafana/
│   ├── provisioning/
│   │   ├── datasources/datasources.yml
│   │   └── dashboards/dashboards.yml  # Provider
│   └── dashboards/                    # JSONs cargados en caliente
│       ├── node-exporter-full.json
│       ├── blackbox.json
│       └── loki-logs.json
├── loki/loki-config.yml               # Con retención 30d
├── promtail/promtail-config.yml
└── blackbox/blackbox.yml
```

**Servicios levantados:**

| Servicio | Imagen | Puerto | Rol |
|---|---|---|---|
| prometheus | `prom/prometheus:v2.55.1` | 9090 | TSDB + scraping |
| grafana | `grafana/grafana:11.3.1` | 3000 | UI de métricas y logs |
| loki | `grafana/loki:3.2.1` | 3100 | Logs centralizados |
| promtail | `grafana/promtail:3.2.1` | — | Ingesta de logs de Sauron |
| blackbox | `prom/blackbox-exporter:v0.25.0` | 9115 | Sondas externas (HTTP/ICMP/TCP) |

---

## 📦 Instalación de Docker (repo oficial)

```bash
apt update
apt install -y ca-certificates curl gnupg

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg \
  | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/debian bookworm stable" \
  | tee /etc/apt/sources.list.d/docker.list > /dev/null

apt update
apt install -y docker-ce docker-ce-cli containerd.io \
               docker-buildx-plugin docker-compose-plugin

systemctl enable --now docker
docker run --rm hello-world
```

> [!tip] /etc/hosts con el mapa de la LAN
> ```bash
> cat >> /etc/hosts << 'EOF'
> 192.168.1.200   leia
> 192.168.1.201   sauron
> 192.168.1.202   matrix
> 192.168.1.203   heimdall
> 192.168.1.210   fallback
> 192.168.1.99    esxi
> EOF
> ```

---

## ⚙️ Estructura y `.env`

```bash
mkdir -p /opt/monitoring/{prometheus,grafana/provisioning/{datasources,dashboards},grafana/dashboards,loki,promtail,blackbox}

cat > /opt/monitoring/.env << 'EOF'
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=CAMBIAR_antes_de_arrancar
EOF

chmod 600 /opt/monitoring/.env
```

---

## ⚙️ `docker-compose.yml`

```yaml
networks:
  monitoring:
    driver: bridge

volumes:
  prometheus_data:
  grafana_data:
  loki_data:

services:

  prometheus:
    image: prom/prometheus:v2.55.1
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
    image: grafana/grafana:11.3.1
    container_name: grafana
    restart: unless-stopped
    ports:
      - "3000:3000"
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana/provisioning:/etc/grafana/provisioning:ro
      - ./grafana/dashboards:/var/lib/grafana/dashboards:ro
    environment:
      - GF_SECURITY_ADMIN_USER=${GRAFANA_ADMIN_USER}
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_ADMIN_PASSWORD}
      - GF_METRICS_ENABLED=true
      - GF_USERS_ALLOW_SIGN_UP=false
    networks:
      - monitoring

  loki:
    image: grafana/loki:3.2.1
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
    image: grafana/promtail:3.2.1
    container_name: promtail
    restart: unless-stopped
    volumes:
      - /var/log:/var/log:ro
      - ./promtail/promtail-config.yml:/etc/promtail/promtail-config.yml:ro
    command: -config.file=/etc/promtail/promtail-config.yml
    networks:
      - monitoring

  blackbox:
    image: prom/blackbox-exporter:v0.25.0
    container_name: blackbox
    restart: unless-stopped
    ports:
      - "9115:9115"
    volumes:
      - ./blackbox/blackbox.yml:/etc/blackbox_exporter/config.yml:ro
    networks:
      - monitoring
```

---

## ⚙️ `prometheus/prometheus.yml`

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s
  external_labels:
    cluster: saasphere
    environment: production

scrape_configs:

  - job_name: prometheus
    static_configs:
      - targets: ['localhost:9090']

  - job_name: node_exporter
    static_configs:
      - targets:
          - 'sauron:9100'
          - 'heimdall:9100'
        labels:
          role: infra

  - job_name: blackbox_http
    metrics_path: /probe
    params:
      module: [http_2xx]
    static_configs:
      - targets:
          - https://www.google.com   # placeholder hasta que haya dominios de cliente
    relabel_configs:
      - source_labels: [__address__]
        target_label: __param_target
      - source_labels: [__param_target]
        target_label: instance
      - target_label: __address__
        replacement: blackbox:9115

  - job_name: loki
    static_configs:
      - targets: ['loki:3100']

  - job_name: grafana
    static_configs:
      - targets: ['grafana:3000']
```

---

## ⚙️ `loki/loki-config.yml` (con retención real)

```yaml
auth_enabled: false

server:
  http_listen_port: 3100
  grpc_listen_port: 9096

common:
  instance_addr: 127.0.0.1
  path_prefix: /loki
  storage:
    filesystem:
      chunks_directory: /loki/chunks
      rules_directory: /loki/rules
  replication_factor: 1
  ring:
    kvstore:
      store: inmemory

schema_config:
  configs:
    - from: 2024-01-01
      store: tsdb
      object_store: filesystem
      schema: v13
      index:
        prefix: index_
        period: 24h

storage_config:
  tsdb_shipper:
    active_index_directory: /loki/tsdb-index
    cache_location: /loki/tsdb-cache
  filesystem:
    directory: /loki/chunks

compactor:
  working_directory: /loki/compactor
  compaction_interval: 10m
  retention_enabled: true
  retention_delete_delay: 2h
  retention_delete_worker_count: 150
  delete_request_store: filesystem

limits_config:
  retention_period: 720h            # 30 días
  reject_old_samples: true
  reject_old_samples_max_age: 168h
  allow_structured_metadata: true
  volume_enabled: true

ruler:
  storage:
    type: local
    local:
      directory: /loki/rules
  rule_path: /loki/rules-temp
  alertmanager_url: ""
  ring:
    kvstore:
      store: inmemory
  enable_api: true
```

---

## ⚙️ `promtail/promtail-config.yml`

```yaml
server:
  http_listen_port: 9080
  grpc_listen_port: 0

positions:
  filename: /tmp/positions.yaml

clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:

  - job_name: system
    static_configs:
      - targets:
          - localhost
        labels:
          job: varlogs
          host: sauron
          __path__: /var/log/*.log

  - job_name: syslog
    static_configs:
      - targets:
          - localhost
        labels:
          job: syslog
          host: sauron
          __path__: /var/log/syslog*
```

---

## ⚙️ `blackbox/blackbox.yml`

```yaml
modules:

  http_2xx:
    prober: http
    timeout: 10s
    http:
      method: GET
      preferred_ip_protocol: ip4
      valid_status_codes: [200, 201, 204, 301, 302]

  http_2xx_ssl:
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

---

## ⚙️ Provisioning de Grafana

### `grafana/provisioning/datasources/datasources.yml`

```yaml
apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: false

  - name: Loki
    type: loki
    access: proxy
    url: http://loki:3100
    editable: false
```

### `grafana/provisioning/dashboards/dashboards.yml`

```yaml
apiVersion: 1

providers:
  - name: 'saasphere'
    orgId: 1
    folder: 'SaaSphere'
    type: file
    disableDeletion: false
    updateIntervalSeconds: 30
    allowUiUpdates: true
    options:
      path: /var/lib/grafana/dashboards
      foldersFromFilesStructure: true
```

### Dashboards de la comunidad descargados

```bash
cd /opt/monitoring/grafana/dashboards

curl -sSL "https://grafana.com/api/dashboards/1860/revisions/latest/download"  -o node-exporter-full.json
curl -sSL "https://grafana.com/api/dashboards/7587/revisions/latest/download"  -o blackbox.json
curl -sSL "https://grafana.com/api/dashboards/13639/revisions/latest/download" -o loki-logs.json
```

| Dashboard | ID Grafana.com | Uso |
|---|---|---|
| Node Exporter Full | 1860 | Métricas detalladas por host |
| Blackbox Exporter | 7587 | Uptime y latencia de sondas |
| Loki Logs / App | 13639 | Explorador de logs por etiqueta |

---

## 🔐 UFW

```bash
ufw allow from 192.168.1.0/24 to any port 9090 proto tcp comment 'Prometheus'
ufw allow from 192.168.1.0/24 to any port 3000 proto tcp comment 'Grafana'
ufw allow from 192.168.1.0/24 to any port 3100 proto tcp comment 'Loki'
ufw allow from 192.168.1.0/24 to any port 9115 proto tcp comment 'Blackbox exporter'
ufw reload
```

---

## 🚀 Puesta en marcha y validación

```bash
cd /opt/monitoring

# Validación de sintaxis antes de levantar
docker compose config > /dev/null && echo "compose OK"

docker run --rm --entrypoint promtool \
  -v /opt/monitoring/prometheus:/etc/prometheus \
  prom/prometheus:v2.55.1 check config /etc/prometheus/prometheus.yml

docker run --rm -v /opt/monitoring/loki:/etc/loki \
  grafana/loki:3.2.1 -config.file=/etc/loki/loki-config.yml -verify-config

docker run --rm --entrypoint /bin/blackbox_exporter \
  -v /opt/monitoring/blackbox:/etc/blackbox \
  prom/blackbox-exporter:v0.25.0 \
  --config.check --config.file=/etc/blackbox/blackbox.yml

# Arranque
docker compose up -d
docker compose ps
```

---

## ✅ Verificación

```bash
curl -s http://localhost:9090/-/healthy    # Prometheus Server is Healthy.
curl -s http://localhost:9090/-/ready      # Prometheus Server is Ready.
curl -s http://localhost:3100/ready        # ready
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000/api/health   # 200
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:9115/             # 200

# Targets activos en Prometheus
curl -s 'http://localhost:9090/api/v1/targets?state=active' \
  | grep -oE '"instance":"[^"]+","job":"[^"]+"' | sort -u
```

> [!success] Targets activos confirmados
> ```
> grafana:3000            job=grafana
> heimdall:9100           job=node_exporter
> https://www.google.com  job=blackbox_http
> localhost:9090          job=prometheus
> loki:3100               job=loki
> sauron:9100             job=node_exporter
> ```

---

## ⚠️ Problemas encontrados

| Problema | Causa | Solución |
|---|---|---|
| `apt install -y docker.io` se mezclaba con el plan original | Dos orígenes distintos de Docker entre Sauron y Matrix | Se unifica todo al repo oficial de Docker (Bookworm sobre Trixie), igual que Matrix |
| `systemctl status node_exporter` → `Unit could not be found` | La plantilla instala el paquete Debian, cuyo unit se llama `prometheus-node-exporter.service` | No es error: ya estaba `active running`. Solo se corrigió el nombre del servicio esperado |
| `promtool check config` fallaba con `unexpected promtool` | El entrypoint de `prom/prometheus` es `/bin/prometheus`, no `promtool` | Sobrescribir con `--entrypoint promtool` al lanzar el contenedor efímero |
| Promtail en `Restarting` con `read /etc/promtail/promtail-config.yml: is a directory` | Al arrancar el contenedor antes de crear el archivo, Docker creó automáticamente un **directorio vacío** con ese nombre en el host | `docker compose stop promtail` → `rm -rf promtail/promtail-config.yml` → recrear como archivo → `docker compose rm -fs promtail` + `up -d` (el `rm -fs` es imprescindible: sin eso el contenedor sigue con el mount cacheado) |
| `docker compose config` → `additional properties 'grafana' not allowed` | El `nano` dejó el archivo con `grafana:` al nivel raíz, fuera de `services:` | Reescribir el compose entero con heredoc (más fiable que editar con nano en consolas donde se mezclan tabs/espacios) |
| Login en Grafana bloqueado con `invalid password` y luego `too many consecutive incorrect login attempts` | Varios intentos fallidos activaron el bloqueo en memoria de Grafana. El CLI `reset-admin-password` **no** limpia ese contador | `docker compose restart grafana` para limpiar el contador en memoria, **después** `grafana cli admin reset-admin-password 'NUEVA'`, después login vía `curl -u admin:'NUEVA'` para descartar cache del navegador |
| Verificar existencia del usuario admin | La CLI de Grafana no tiene un comando para listar usuarios; la imagen no trae `sqlite3` | Contenedor efímero de Alpine montando el volumen `monitoring_grafana_data`: `alpine sh -c "apk add sqlite && sqlite3 /data/grafana.db 'SELECT id, login, email FROM user;'"` |

---

## 📎 Notas y próximos pasos

**Pendiente para cerrar la monitorización al 100%:**

- [ ] Alertmanager + reglas de alertas (instance down, disco > 85 %, RAM > 90 %, `probe_success == 0`, certificado SSL a < 14 días)
- [ ] Notificación por Telegram (bot + chat_id) **y** email (Gmail con app password, SMTP `smtp.gmail.com:587`)
- [ ] Recogida de logs de los contenedores Docker de Sauron (añadir a Promtail el discovery de `/var/lib/docker/containers/*/*.log` o usar el driver de logs `loki`)

**Targets que se añadirán a Prometheus conforme se levanten otros nodos:**

| Nodo | Targets a añadir |
|---|---|
| Matrix | `matrix:9100`, `kube-state-metrics:8080`, `cAdvisor:8080`, Traefik metrics |
| Fallback | `fallback:9100` + Promtail-agent |
| LeIA | `leia:9100`, `ollama-exporter`, `dcgm-exporter` (GPU) |
| ESXi | `vmware_exporter` (corre en Sauron, apunta a la API de ESXi) |
| Blackbox | Sustituir placeholder por dominios reales de cliente |

> [!tip] Patrón de secretos
> Cualquier credencial nueva (bot Telegram, SMTP, etc.) se añade a `/opt/monitoring/.env` (`chmod 600`) y se referencia con `${VAR}` en el compose o los configs. Nunca hardcodeado.

> [!warning] Blackbox con placeholder
> El target `https://www.google.com` está ahí solo para validar que el job funciona end-to-end. Debe reemplazarse por los dominios de cliente en cuanto haya al menos uno desplegado en Matrix.

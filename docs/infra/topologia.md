# Topología del homelab SaaSphere

Inventario físico y lógico de las máquinas que componen el TFG. Todas conviven en la LAN doméstica `192.168.1.0/24` y se ven entre sí por hostname (resolución vía `/etc/hosts` en cada nodo).

## Tabla de nodos

| Hostname  | IP            | Rol                        | OS              | Servicios principales |
|-----------|---------------|----------------------------|-----------------|------------------------|
| `leia`    | 192.168.1.200 | Agente IA orquestador      | Debian Trixie   | **Lobster** (FastAPI + aiogram), **Ollama** (qwen3:8b / qwen3:32b), samba |
| `sauron`  | 192.168.1.201 | Observabilidad             | Debian Trixie   | **Prometheus**, **Grafana**, **Loki**, **Alertmanager**, **Promtail**, **Blackbox exporter** |
| `matrix`  | 192.168.1.202 | Orquestación contenedores  | Debian Trixie   | **K3s** (server), **Docker**, **Registry privado**, kube-state-metrics |
| `heimdall`| 192.168.1.203 | Gateway / VPN              | Debian Trixie   | **WireGuard**, bots Telegram (Wake-on-LAN), node_exporter |
| `fallback`| 192.168.1.210 | Reserva / failover         | —               | Nodo de respaldo (planificado) |
| `saasphere.saasphere.local` | 192.168.1.240 | VIP MetalLB | — | IP virtual del ingress del primer tenant (`saasphere`) |

Todos los nodos exponen **`prometheus-node-exporter`** en `:9100`, scraped por el Prometheus de Sauron.

## Diagrama lógico

```
                        ┌──────────────────────────────────────────────┐
                        │           LAN 192.168.1.0/24                 │
                        └──────────────────────────────────────────────┘

  ┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
  │     leia .200    │     │    sauron .201   │     │    matrix .202   │
  │                  │     │                  │     │                  │
  │  Lobster :8080   │◀───▶│  Prometheus      │◀───▶│  K3s API :6443   │
  │   FastAPI        │     │   :9090          │     │                  │
  │   Telegram bot   │     │  Grafana :3000   │     │  Registry :5000  │
  │                  │     │  Loki    :3100   │     │                  │
  │  Ollama :11434   │     │  Alertmanager    │     │  Tenants ns:     │
  │   qwen3:8b/32b   │     │     :9093        │     │   tenant-*       │
  └────────┬─────────┘     └─────────┬────────┘     └─────────┬────────┘
           │                         │                        │
           │  /webhook/alert         │  scrape :9100 + :8080  │
           ◀─────────────────────────┘  + apps (cadvisor)     │
           │                                                  │
           │           kubeconfig (token RBAC limitado)       │
           └─────────────────────────────────────────────────▶│
                                                              │
                                              ┌───────────────┴──────────────┐
                                              │   MetalLB VIP .240           │
                                              │   ingress → saasphere tenant │
                                              └──────────────────────────────┘

  ┌──────────────────┐                           ┌──────────────────┐
  │   heimdall .203  │                           │   fallback .210  │
  │                  │                           │                  │
  │  WireGuard wg0   │                           │   (reserva)      │
  │  Bots Telegram   │                           │                  │
  │   Wake-on-LAN    │─── magic packet WoL ──▶   │                  │
  │  node_exporter   │                           │                  │
  └──────────────────┘                           └──────────────────┘
```

## Flujos clave

- **Detección de incidente**: Prometheus (Sauron) detecta una regla disparada → Alertmanager la enruta dualmente:
  - **Vía Lobster**: webhook a `http://leia:8080/webhook/alert` → el agente decide si aplicar una mutación (con/sin aprobación humana en Telegram).
  - **Vía Telegram directo**: bot independiente envía la alerta al chat del operador (defensa en profundidad si Lobster está caído).
- **Mutación**: Lobster valida con la policy (`LeIA/opt/lobster/lobster_agent/domain/policy.py`), pide aprobación si la severidad lo exige, y ejecuta vía la API de K3s con el token RBAC en `LeIA/etc/lobster/kubeconfig` (cuenta `openclaw-reader` definida en `Matrix/opt/k3s/leia-rbac.yaml`).
- **Persistencia**: SQLite local en LeIA (`/var/lib/lobster/lobster.db`). Migraciones Alembic en `LeIA/opt/lobster/alembic/versions/`.
- **Modelos IA**: Ollama (LeIA) sirve `qwen3:8b` para lectura/fast y `qwen3:32b` para análisis/mutaciones. Modelos en `/mnt/modelos/ollama/models` (partición dedicada).

## Convención de carpetas en este repo

Cada carpeta de nodo replica el filesystem real de su máquina. Por ejemplo, un archivo del repo en `Sauron/opt/monitoring/prometheus/prometheus.yml` se despliega en la máquina `sauron` en la ruta `/opt/monitoring/prometheus/prometheus.yml`. Esto facilita que la documentación y el despliegue sean coherentes 1:1.

## Política de secretos

Ningún secreto se commitea en este repo. Para cada archivo con credenciales hay un `.example` con placeholders junto al real ignorado por `.gitignore`. Lista de placeholders:

| Archivo en máquina                                           | Plantilla en repo                                                     |
|--------------------------------------------------------------|-----------------------------------------------------------------------|
| `/etc/lobster/.env` (LeIA)                                   | `LeIA/etc/lobster/.env.example`                                       |
| `/etc/lobster/kubeconfig` (LeIA)                             | `LeIA/etc/lobster/kubeconfig.example`                                 |
| `/opt/monitoring/alertmanager/alertmanager.yml` (Sauron)     | `Sauron/opt/monitoring/alertmanager/alertmanager.yml.example`         |
| `/etc/rancher/k3s/k3s.yaml` (Matrix)                         | `Matrix/etc/rancher/k3s/k3s.yaml.example` *(pendiente)*               |
| `/etc/wireguard/wg0.conf` (Heimdall)                         | `Heimdall/etc/wireguard/wg0.conf.example` *(pendiente)*               |

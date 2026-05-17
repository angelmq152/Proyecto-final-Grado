## 🗺️ Contexto

|Parámetro|Valor|
|---|---|
|Nodo|Heimdall (VM en ESXi)|
|SO|Debian Trixie (minimal)|
|IP local|`192.168.1.203`|
|Rol|Servidor VPN (WireGuard)|
|RAM|512 MB|
|Puerto de métricas|`:9100` (todo vía node_exporter)|

> [!info] Estrategia de monitorización Heimdall no tiene Docker. Todos los exporters se integran a través del **textfile collector de node_exporter**, que lee archivos `.prom` generados por scripts y los expone en el mismo puerto `:9100`. Cero servicios adicionales, cero overhead.

---

## 📦 Exporters instalados

|#|Exporter|Método|Puerto|
|---|---|---|---|
|1|`node_exporter`|Servicio systemd nativo (`apt`)|`:9100`|
|2|WireGuard (textfile)|Script bash + timer systemd|`:9100`|
|3|Fail2ban (textfile)|Script Python + timer systemd|`:9100`|

---

## ⚙️ 1. Node Exporter

Instalado desde la plantilla base Debian vía `apt`. Configurado con el **textfile collector** habilitado para que recoja los `.prom` de los otros exporters.

```bash
# /etc/default/prometheus-node-exporter
ARGS="--collector.textfile.directory=/var/lib/prometheus/node-exporter"
```

```bash
# Directorio de textfiles
mkdir -p /var/lib/prometheus/node-exporter
chown prometheus:prometheus /var/lib/prometheus/node-exporter
```

```bash
systemctl restart prometheus-node-exporter
```

> [!tip] Scrape en Sauron Apuntar el job `node` en `prometheus.yml` a `heimdall:9100` para recoger tanto las métricas del sistema como las de WireGuard y Fail2ban en una sola diana.

---

## ⚙️ 2. WireGuard Exporter (textfile)

> [!note] Decisión: textfile collector frente a binario externo Los repositorios de exporters WireGuard con binarios precompilados (MindFlavor, kbknapp) están abandonados y sus releases devuelven 404. La alternativa de script bash + textfile collector es más ligera, sin dependencias, y encaja perfectamente con los 512 MB de Heimdall.

### Script

```bash
# /usr/local/bin/wg-metrics.sh
#!/bin/bash
OUTPUT="/var/lib/prometheus/node-exporter/wireguard.prom"
TMPFILE=$(mktemp)

echo "# HELP wireguard_peer_receive_bytes_total Bytes received from peer" > $TMPFILE
echo "# TYPE wireguard_peer_receive_bytes_total counter" >> $TMPFILE
echo "# HELP wireguard_peer_transmit_bytes_total Bytes sent to peer" >> $TMPFILE
echo "# TYPE wireguard_peer_transmit_bytes_total counter" >> $TMPFILE
echo "# HELP wireguard_peer_last_handshake_seconds Timestamp of last handshake" >> $TMPFILE
echo "# TYPE wireguard_peer_last_handshake_seconds gauge" >> $TMPFILE

wg show all dump | tail -n +2 | while read iface pubkey preshared endpoint allowed rx tx handshake keepalive; do
    echo "wireguard_peer_receive_bytes_total{interface=\"$iface\",peer=\"$pubkey\"} $rx" >> $TMPFILE
    echo "wireguard_peer_transmit_bytes_total{interface=\"$iface\",peer=\"$pubkey\"} $tx" >> $TMPFILE
    echo "wireguard_peer_last_handshake_seconds{interface=\"$iface\",peer=\"$pubkey\"} $handshake" >> $TMPFILE
done

mv $TMPFILE $OUTPUT
chown prometheus:prometheus $OUTPUT
```

```bash
chmod +x /usr/local/bin/wg-metrics.sh
```

### Servicio y timer systemd

```ini
# /etc/systemd/system/wg-metrics.service
[Unit]
Description=WireGuard metrics para node_exporter

[Service]
Type=oneshot
ExecStart=/usr/local/bin/wg-metrics.sh
```

```ini
# /etc/systemd/system/wg-metrics.timer
[Unit]
Description=Ejecutar wg-metrics cada minuto

[Timer]
OnBootSec=30s
OnUnitActiveSec=1min

[Install]
WantedBy=timers.target
```

```bash
systemctl daemon-reload
systemctl enable --now wg-metrics.timer
```

### Métricas expuestas

|Métrica|Tipo|Descripción|
|---|---|---|
|`wireguard_peer_receive_bytes_total`|counter|Bytes recibidos por peer|
|`wireguard_peer_transmit_bytes_total`|counter|Bytes enviados por peer|
|`wireguard_peer_last_handshake_seconds`|gauge|Timestamp del último handshake|

### ✅ Verificación

```bash
/usr/local/bin/wg-metrics.sh
cat /var/lib/prometheus/node-exporter/wireguard.prom
```

Ejemplo de salida con un peer activo (iPhone):

```
wireguard_peer_receive_bytes_total{interface="wg0",peer="SPP/tMIy..."} 1775509270
wireguard_peer_transmit_bytes_total{interface="wg0",peer="SPP/tMIy..."} 83568
wireguard_peer_last_handshake_seconds{interface="wg0",peer="SPP/tMIy..."} 64976
```

> [!success] Estado Peers desconectados muestran `0` en las tres métricas. Peers activos muestran tráfico real y handshake reciente.

---

## ⚙️ 3. Fail2ban Exporter (textfile)

> [!note] Decisión: script Python frente a binario externo El exporter oficial (hctrdev/fail2ban-prometheus-exporter) no publica binarios estáticos descargables en sus releases. Se usa el script de jangrewe que emplea `fail2ban-client` directamente y escribe al textfile collector. Python ya viene instalado en Debian, sin dependencias adicionales.

### Script

```bash
wget https://raw.githubusercontent.com/jangrewe/prometheus-fail2ban-exporter/master/fail2ban-exporter.py \
  -O /usr/local/bin/fail2ban-metrics.py
chmod +x /usr/local/bin/fail2ban-metrics.py
```

### Servicio y timer systemd

```ini
# /etc/systemd/system/fail2ban-metrics.service
[Unit]
Description=Fail2ban metrics para node_exporter
After=fail2ban.service

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /usr/local/bin/fail2ban-metrics.py
```

```ini
# /etc/systemd/system/fail2ban-metrics.timer
[Unit]
Description=Ejecutar fail2ban-metrics cada minuto

[Timer]
OnBootSec=30s
OnUnitActiveSec=1min

[Install]
WantedBy=timers.target
```

```bash
systemctl daemon-reload
systemctl enable --now fail2ban-metrics.timer
```

### Métricas expuestas

|Métrica|Tipo|Descripción|
|---|---|---|
|`fail2ban_failed_current`|gauge|Intentos fallidos activos por jail|
|`fail2ban_failed_total`|gauge|Total histórico de fallos por jail|
|`fail2ban_banned_current`|gauge|IPs baneadas actualmente por jail|
|`fail2ban_banned_total`|gauge|Total histórico de baneos por jail|

### ✅ Verificación

```bash
python3 /usr/local/bin/fail2ban-metrics.py
cat /var/lib/prometheus/node-exporter/fail2ban.prom
```

Ejemplo de salida tras prueba de baneo:

```
fail2ban_failed_total{jail="sshd"} 3.0
fail2ban_banned_current{jail="sshd"} 1.0
fail2ban_banned_total{jail="sshd"} 1.0
```

> [!success] Estado Baneo detectado correctamente tras 3 intentos fallidos de SSH desde cliente externo.

> [!warning] SyntaxWarning en Python El script muestra dos `SyntaxWarning` por regex con escape sequences antiguas. Son inocuos y no afectan al funcionamiento ni a las métricas generadas.

---

## 📊 Configuración en Sauron (prometheus.yml)

```yaml
scrape_configs:
  - job_name: 'node'
    static_configs:
      - targets:
          - 'heimdall:9100'
```

> [!info] Un solo target, tres exporters Con un único job apuntando a `heimdall:9100`, Prometheus recoge automáticamente las métricas del sistema, de WireGuard y de Fail2ban. El textfile collector las fusiona todas en el mismo endpoint.

---

## ⚠️ Problemas encontrados

|Problema|Causa|Solución|
|---|---|---|
|`wget` de MindFlavor devuelve 404|El repo no publica binarios en sus releases|Sustituido por script bash + textfile collector|
|`wget` de kbknapp devuelve 404|Mismo problema, repo sin binarios reales|Mismo enfoque|
|`wget` de hctrdev devuelve 404|El exporter oficial tampoco tiene binarios estáticos|Script Python de jangrewe|
|`SyntaxWarning` en fail2ban-metrics.py|Regex con escape sequences deprecadas en Python moderno|Inocuo, no requiere corrección|

---

## 📎 Notas

> [!tip] Reutilización en otras VMs El mismo patrón (textfile collector + timer systemd) puede replicarse en Matrix y en el nodo Fallback para Fail2ban. Solo WireGuard es exclusivo de Heimdall.

_#saasphere #heimdall #prometheus #monitorización #wireguard #fail2ban #node-exporter_
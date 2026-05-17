
> Servidor minimal para VMware ESXi. Base común para 3 VMs: WireGuard, Docker x2.

---

## 1. Sources.list

```bash
# /etc/apt/sources.list

deb http://deb.debian.org/debian trixie main contrib non-free non-free-firmware
deb http://deb.debian.org/debian trixie-updates main contrib non-free non-free-firmware
deb http://security.debian.org/debian-security trixie-security main contrib non-free non-free-firmware
```

```bash
apt update && apt upgrade -y
```

---

## 2. Paquetes instalados

```bash
apt install -y \
  curl vim htop \
  sudo \
  ufw fail2ban openssh-server \
  unattended-upgrades debconf \
  lynis rkhunter auditd \
  prometheus-node-exporter \
  #wireguard wireguard-tools  # Solo VM WireGuard
  # docker.io docker-compose  # Solo VMs Docker
```

---

## 3. PATH global

```bash
# /etc/environment
PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
```

```bash
source /etc/environment
```

---

## 4. Aliases globales

```bash
# /etc/bash.bashrc — al final del archivo
alias c='clear'
```

---

## 5. Seguridad SSH

```bash
# /etc/ssh/sshd_config
PermitRootLogin no
```

```bash
systemctl restart sshd
```

---

## 6. UFW — Firewall

```bash
ufw allow ssh
ufw enable
```

---

## 7. fail2ban

```bash
# /etc/fail2ban/jail.local
[sshd]
enabled = true
maxretry = 5
bantime = 1h
findtime = 10m
```

```bash
systemctl enable fail2ban
systemctl start fail2ban
```

---

## 8. unattended-upgrades

```bash
/usr/sbin/dpkg-reconfigure unattended-upgrades
# Seleccionar YES
```

Verificar:

```bash
cat /etc/apt/apt.conf.d/20auto-upgrades
# Debe mostrar:
# APT::Periodic::Update-Package-Lists "1";
# APT::Periodic::Unattended-Upgrade "1";
```

---

## 9. auditd

```bash
systemctl enable auditd
systemctl start auditd
```

---

## 10. Node Exporter

```bash
systemctl enable prometheus-node-exporter
systemctl start prometheus-node-exporter
# Escucha en puerto 9100
```

Restringir acceso solo a Prometheus (recomendado):

```bash
ufw allow from <IP-prometheus> to any port 9100
```

---

## 11. lynis y rkhunter (uso manual)

```bash
lynis audit system      # Auditoría del sistema
rkhunter --check        # Detección de rootkits
```

No tienen servicio activo, se lanzan manualmente.

---

## 12. Resultado rkhunter inicial

- Ficheros analizados: 140
- Ficheros sospechosos: 1 (sudo — falso positivo normal en Debian)
- Rootkits comprobados: 495
- Rootkits encontrados: 0 ✅

---

## 13. Pasos post-clonación (en cada clon)

|Acción|Comando|
|---|---|
|Cambiar hostname|`hostnamectl set-hostname nombre-vm`|
|Cambiar IP fija|`nano /etc/network/interfaces`|
|Añadir usuario a sudo|`usermod -aG sudo usuario`|

### Solo VM WireGuard (512MB):

```bash
apt install -y wireguard wireguard-tools
```

### Solo VMs Docker:

```bash
apt install -y docker.io docker-compose
```

---

## 14. Arquitectura de monitorización

```
[VM WireGuard]  ──┐
                  ├──→ node-exporter :9100 ──→ [Prometheus + Grafana]
[VM Docker 1]   ──┤
[VM Docker 2]   ──┘
```

- **Node Exporter** en cada VM
- **Prometheus + Grafana** en una de las VMs Docker

---

## Notas

- Trixie es Debian 13 **Testing** — no es stable. Válido para este uso pero tenerlo en cuenta.
- Con 512MB en la VM WireGuard, no instalar Docker. WireGuard nativo consume prácticamente 0 RAM.
- La plantilla NO tiene hostname ni IP fija configurados — se asignan post-clonación.
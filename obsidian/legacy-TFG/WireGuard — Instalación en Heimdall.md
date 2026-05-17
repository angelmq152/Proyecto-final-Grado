

## 🗺️ Contexto

| Parámetro       | Valor                 |
| --------------- | --------------------- |
| Nodo            | Heimdall (VM en ESXi) |
| SO              | Debian 12 (minimal)   |
| Interfaz de red | `ens192`              |
| IP local        | `192.168.1.203`       |
| Red LAN         | `192.168.1.0/24`      |
| Red VPN         | `10.10.0.0/24`        |
| Puerto          | UDP 51820             |

> [!info] Topología elegida **Hub & Spoke**: Heimdall actúa como servidor central. Todos los peers conectan a él. Se eligió frente a Full Mesh por simplicidad operativa y porque encaja con el rol de Heimdall como nodo de red dedicado.

---

## 🏗️ Topología

|Dispositivo|Rol|IP VPN|
|---|---|---|
|Heimdall|Servidor|`10.10.0.1`|
|Portátil (Windows)|Peer 1|`10.10.0.2`|
|iPhone|Peer 2|`10.10.0.3`|
|Peer genérico|Peer 3|`10.10.0.4`|

---

## 📦 Instalación

```bash
sudo apt update && sudo apt install wireguard -y
```

---

## 🔐 Almacén de claves

> [!note] Decisión de diseño Las claves se centralizan en `/etc/wireguard/keys/` con permisos estrictos. Las claves privadas (`.key`) solo son legibles por root. El almacén sirve como backup y referencia; los valores se insertan en texto plano en `wg0.conf`.

```bash
sudo mkdir -p /etc/wireguard/keys
sudo chmod 700 /etc/wireguard/keys
cd /etc/wireguard/keys

# Servidor
wg genkey | sudo tee server.key | wg pubkey | sudo tee server.pub

# Portátil
wg genkey | sudo tee laptop.key | wg pubkey | sudo tee laptop.pub

# iPhone
wg genkey | sudo tee iphone.key | wg pubkey | sudo tee iphone.pub

# Peer genérico
wg genkey | sudo tee generic.key | wg pubkey | sudo tee generic.pub

# Permisos
sudo chmod 600 /etc/wireguard/keys/*.key
sudo chmod 644 /etc/wireguard/keys/*.pub
```

---

## ⚙️ Configuración del servidor

```bash
sudo nano /etc/wireguard/wg0.conf
```

```ini
[Interface]
Address = 10.10.0.1/24
ListenPort = 51820
PrivateKey = <valor de server.key>

PostUp   = iptables -A FORWARD -i wg0 -j ACCEPT; iptables -t nat -A POSTROUTING -o ens192 -j MASQUERADE
PostDown = iptables -D FORWARD -i wg0 -j ACCEPT; iptables -t nat -D POSTROUTING -o ens192 -j MASQUERADE

# --- Portátil ---
[Peer]
PublicKey = <valor de laptop.pub>
AllowedIPs = 10.10.0.2/32

# --- iPhone ---
[Peer]
PublicKey = <valor de iphone.pub>
AllowedIPs = 10.10.0.3/32

# --- Peer genérico ---
[Peer]
PublicKey = <valor de generic.pub>
AllowedIPs = 10.10.0.4/32
```

```bash
sudo chmod 600 /etc/wireguard/wg0.conf
```

> [!warning] Permisos del archivo de configuración Si `wg0.conf` tiene permisos más abiertos que `600`, WireGuard puede negarse a cargarlo.

---

## ⚙️ IP Forwarding

Necesario para enrutar tráfico entre peers y la LAN:

```bash
echo "net.ipv4.ip_forward=1" | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

---

## 🚀 Puesta en marcha

```bash
sudo systemctl enable wg-quick@wg0
sudo systemctl start wg-quick@wg0
```

---

## 🔐 Firewall (UFW)

> [!warning] UFW activo con política DROP Heimdall tiene UFW configurado con política por defecto `DROP`. Sin abrir el puerto explícitamente, el tráfico UDP entrante es bloqueado aunque el port forwarding del router esté correcto.

```bash
sudo ufw allow 51820/udp
sudo ufw reload
sudo ufw status
```

---

## 🌐 Port forwarding en el router

|Campo|Valor|
|---|---|
|Protocolo|UDP|
|Puerto externo|51820|
|Puerto interno|51820|
|IP destino|`192.168.1.203`|

---

## ⚙️ Configuración de clientes

### Portátil — Windows

Instalar cliente desde [wireguard.com/install](https://www.wireguard.com/install/) y crear un túnel nuevo:

```ini
[Interface]
PrivateKey = <valor de laptop.key>
Address = 10.10.0.2/32
DNS = 1.1.1.1

[Peer]
PublicKey = <valor de server.pub>
Endpoint = <IP_PUBLICA>:51820
AllowedIPs = 10.10.0.0/24, 192.168.1.0/24
PersistentKeepalive = 25
```

### iPhone

Crear config en Heimdall y generar QR para la app WireGuard (App Store):

```bash
sudo mkdir -p /etc/wireguard/clients
sudo nano /etc/wireguard/clients/iphone.conf
```

```ini
[Interface]
PrivateKey = <valor de iphone.key>
Address = 10.10.0.3/32
DNS = 1.1.1.1

[Peer]
PublicKey = <valor de server.pub>
Endpoint = <IP_PUBLICA>:51820
AllowedIPs = 10.10.0.0/24, 192.168.1.0/24
PersistentKeepalive = 25
```

```bash
sudo apt install qrencode -y
qrencode -t ansiutf8 < /etc/wireguard/clients/iphone.conf
```

---

## ✅ Verificación

```bash
sudo wg show
```

Una conexión activa muestra:

```
peer: <clave_publica>
  allowed ips: 10.10.0.x/32
  latest handshake: X seconds ago
  transfer: X KiB received, X KiB sent
```

> [!success] Estado final iPhone conectado como peer activo con handshake y transferencia de datos confirmados.

---

## ⚠️ Problemas encontrados

|Problema|Causa|Solución|
|---|---|---|
|`apt` no resuelve dominios|DNS no configurado en la VM|Añadir `nameserver 8.8.8.8` en `/etc/resolv.conf`|
|`wg-quick@wg0` falla al arrancar|WireGuard no acepta rutas de archivo como valor de clave|Sustituir las rutas por el valor en texto plano de cada clave|
|iPhone no conecta|Clave pública usada como `PrivateKey` en el conf del cliente|Usar el valor correcto de `iphone.key`|
|iPhone no conecta (2)|Puerto UDP 51820 bloqueado por UFW|`sudo ufw allow 51820/udp`|
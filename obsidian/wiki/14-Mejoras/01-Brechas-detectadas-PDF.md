---
title: Brechas detectadas — PDF vs Wiki/código
tags: [mejoras, brechas, correcciones, tfg]
---

# 🔍 Brechas detectadas — PDF vs Wiki/código

> [!abstract] La wiki tiene errores
> Esta nota recopila los puntos donde **lo que escribí en la wiki no coincide con la memoria TFG en PDF**. Son la primera prioridad: documentación incorrecta es peor que ausente.

## 🔴 Brechas críticas (la wiki dice algo falso)

### B-01 — Heimdall NO es edge proxy / Traefik / DNS

> [!danger] Error en mi wiki
> Mi nota [[../08-Infraestructura/03-Hosts-LeIA-Sauron-Heimdall#Heimdall · edge]] dice:
> > *"Traefik que reenvía hacia matrix. Cert-manager / Let's Encrypt para dominios reales. DNS de `*.saasphere.local`."*
>
> **El PDF dice (página 3)**: *"Heimdall: Puerta VPN, brinda acceso remoto seguro"*. Su único servicio es **WireGuard** (página 25). Es 1GB RAM, 1 vCPU.
>
> **Traefik y cert-manager viven en MATRIX**, no en Heimdall. Matrix también aloja el registry privado v2 en :5000.

**Acción**: corregir [[../08-Infraestructura/03-Hosts-LeIA-Sauron-Heimdall]] y [[../08-Infraestructura/01-SaaSphere-cluster-K3s#DNS]].

### B-02 — Existe un nodo ESXi físico no documentado

> [!danger] Hay un nodo que no está en la wiki
> El PDF documenta **5 nodos**, no 5 hosts. Uno es **ESXi**: servidor físico que aloja Heimdall, Sauron y Matrix como **VMs**.
>
> Especificaciones (PDF página 19): *"4x Intel Xeon E31220 @ 3.10 GHz · 12 GB RAM (10 GB disponibles, 2 GB para hipervisor) · 3 TB disco"*.

**Acción**: añadir nota nueva `08-Infraestructura/07-ESXi-hipervisor.md` y actualizar el diagrama de topología en [[../01-Arquitectura/03-Topologia-homelab]].

### B-03 — Hardware específico no documentado

> [!danger] Faltan especificaciones reales
> El PDF lista hardware concreto. La wiki solo habla genéricamente.

| Nodo | Hardware real (PDF) |
|---|---|
| **LeIA** | PC escritorio · Intel Core i9-12900KF · 32 GB RAM · 100 GB SSD + 500 GB HDD · NVIDIA RTX 3060 Ti 8GB VRAM · Debian 13 |
| **ESXi** | Servidor físico · 4x Intel Xeon E31220 @ 3.10 GHz · 12 GB RAM (10 GB para VMs) · 3 TB · VMware ESXi 7 |
| **Fallback** | **Portátil reutilizado** · Intel Pentium 2020M @ 2.40 GHz · 4 GB RAM · 750 GB disco · Debian 13 |
| **Heimdall** (VM) | Debian 13 · 1 GB RAM · 1 vCPU · 50 GB |
| **Sauron** (VM) | Debian 13 · 3 GB RAM · 1 vCPU · 100 GB |
| **Matrix** (VM) | Debian 13 · 6 GB RAM · 3 vCPU · 500 GB |

**Acción**: añadir todo esto en [[../08-Infraestructura/03-Hosts-LeIA-Sauron-Heimdall]] y crear una tabla maestra de hardware.

### B-04 — IP de Fallback errónea / Fallback como nodo K3s real

> [!danger] No tengo la IP correcta
> Mi wiki dice "Fallback: (local)" sin IP. **El PDF dice (página 22) `192.168.1.210`** y es un portátil físico independiente, no una VM.

Además, en el PDF (página 23) las IPs de las VMs son:
- Sauron: `192.168.1.201`
- Matrix: `192.168.1.202`
- Heimdall: `192.168.1.203` ← mi wiki decía "edge" sin IP.

El servidor físico ESXi tiene IP `192.168.1.99` (página 22 del PDF).

**Acción**: actualizar [[../08-Infraestructura/03-Hosts-LeIA-Sauron-Heimdall]] y el diagrama Mermaid en [[../01-Arquitectura/03-Topologia-homelab]].

### B-05 — Sauron usa Docker Compose, no Kubernetes

> [!danger] Detalle importante de despliegue
> La wiki no lo aclara: en Sauron, Prometheus + Grafana + Loki + Alertmanager + Blackbox + Promtail corren como **6 contenedores Docker Compose** en `/opt/monitoring/`. Estructura del PDF (página 28):
>
> ```
> /opt/monitoring/
> ├── alertmanager/alertmanager.yml
> ├── blackbox/blackbox.yml
> ├── docker-compose.yml
> ├── grafana/
> │   ├── dashboards/{blackbox.json, loki-logs.json, node-exporter-full.json}
> │   └── provisioning/{dashboards.yml, datasources.yml}
> ├── loki/loki-config.yml
> ├── prometheus/
> │   ├── prometheus.yml
> │   └── rules/saasphere.yml
> └── promtail/promtail-config.yml
> ```
> Red docker interna: `172.18.0.0/16`.

**Acción**: documentar en [[../06-Observabilidad/00-MOC-Observabilidad]] y añadir nota dedicada.

### B-06 — Modelo de negocio (productos, soporte, precios) NO existe en la wiki

> [!danger] La wiki es 100% técnica
> El PDF dedica ~5 páginas (12-15) a productos comerciales, niveles de soporte, costes y rentabilidad. **Nada de esto está en la wiki**. Mientras Lobster siga siendo un agente de SaaSphere como negocio, esto es crítico.

→ Cubierto en [[03-Mejoras-negocio-y-producto]].

### B-07 — Dificultad técnica real ignorada: drivers NVIDIA/CUDA

> [!danger] Apartado "Mayores dificultades" del PDF
> El PDF dedica una sección entera a la **batalla contra CUDA en Debian 13 trixie** (página 67):
>
> > *"ggml_cuda_init: failed to initialize CUDA: unknown error […] Hipótesis 5: Mala relación entre Ollama y los Drivers […] hubo que actualizar los drivers sin emplear las librerías oficiales de Debian, de manera manual y compilándolos a mano […] purgue los drivers actuales y desde la línea de comando pura instale los drivers y configure Nvidia-driver-595."*
>
> Esto es **una de las experiencias técnicas más valiosas del proyecto**. Mi wiki no lo menciona en absoluto.

**Acción**: añadir a [[../10-Operacion/07-Troubleshooting]] una sección "CUDA/NVIDIA en Debian 13 trixie".

## 🟠 Brechas importantes (la wiki no miente, pero omite)

### B-08 — Configuración WireGuard concreta

WireGuard en Heimdall (PDF página 25):
- Interfaz física: `ens192`
- Red VPN: `10.10.0.0/24`
- Puerto: `UDP 51820`
- IP Heimdall VPN: `10.10.0.1/24`
- Claves en `/etc/wireguard/keys/<nombre_clave>`
- Configuración: `/etc/wireguard/wg0.conf`
- 3 claves iniciales (portátil, móvil, genérica)

**Acción**: añadir `08-Infraestructura/08-VPN-WireGuard.md`.

### B-09 — Servicios base por nodo

PDF página 23: cada VM lleva una base estándar:
- `/etc/apt/sources.list` con Debian 13 Trixie
- Paquetes: `curl, vim, htop, sudo, openssh-server`
- Seguridad: `fail2ban, ufw, auditd`, `PermitRootLogin deshabilitado`, `unattended-upgrades`
- Monitorización: `prometheus-node-exporter` en `:9100`
- Auditoría: `lynis, rkhunter`
- Sistema: PATH global, alias `c=clear`, IP estática con hotplug

**Acción**: documentar en [[../08-Infraestructura/06-Systemd-deploy]] como "baseline de host".

### B-10 — Token de Matrix para Fallback en K3s

PDF página 39: *"Se ha usado el token de autenticación de matrix para instalar el agente en Fallback, permitiendo así lanzar los contenedores ahí en caso de que matrix no pueda."*

**Acción**: documentar en [[../08-Infraestructura/02-Nodos-matrix-fallback]] cómo se une fallback al control plane.

### B-11 — Registry privado Docker v2 en Matrix:5000

Mi wiki no lo menciona. El PDF (página 36) explica que `192.168.1.202:5000` es un registry privado interno **sin TLS**, configurado con confianza en `/etc/rancher/k3s/registries.yaml`. Almacena las imágenes de los tenants.

**Acción**: añadir nota dedicada al registry.

## 🟡 Brechas deseables (detalles que aportarían riqueza)

### B-12 — Frase emblemática del proyecto

PDF página 3: *"Un tonto le ha dicho a un listo que hacer"*. Es la **filosofía** del proyecto: la IA local "pequeña" puede hacer cosas grandes porque alguien más capaz le ha diseñado las herramientas.

**Acción**: incluir en [[../01-Arquitectura/01-Vision-general]] como cita.

### B-13 — Plantilla VM y proceso de creación

PDF página 23: *"Instalación realizada correctamente partiendo de una VM plantilla, todas las máquinas tienen la misma configuración exceptuando hostname y dirección IP."* En vSphere/ESXi se ve la VM template llamada `SaaSphere`.

**Acción**: documentar como tip operativo.

---

## 📋 Checklist de correcciones

> [!example] Para arreglar la wiki después de leer esto
> - [ ] Corregir [[../08-Infraestructura/03-Hosts-LeIA-Sauron-Heimdall]] — Heimdall = solo VPN, Traefik = Matrix.
> - [ ] Crear `08-Infraestructura/07-ESXi-hipervisor.md`.
> - [ ] Crear `08-Infraestructura/08-VPN-WireGuard.md`.
> - [ ] Crear `08-Infraestructura/09-Docker-Compose-Sauron.md`.
> - [ ] Crear `08-Infraestructura/10-Registry-Matrix-5000.md`.
> - [ ] Añadir sección hardware real en [[../08-Infraestructura/03-Hosts-LeIA-Sauron-Heimdall]].
> - [ ] Añadir tabla IPs reales en [[../08-Infraestructura/01-SaaSphere-cluster-K3s]].
> - [ ] Actualizar diagrama Mermaid en [[../01-Arquitectura/03-Topologia-homelab]].
> - [ ] Añadir sección CUDA/NVIDIA en [[../10-Operacion/07-Troubleshooting]].
> - [ ] Crear sección 15-Negocio o ampliar 09-Tenants con productos comerciales.
> - [ ] Añadir cita "Un tonto le ha dicho a un listo qué hacer" en [[../01-Arquitectura/01-Vision-general]].

# Heimdall

Nodo de **gateway / VPN** del homelab SaaSphere. *Placeholder* — pendiente de implementación.

## Servicios planificados

- **WireGuard** ([`etc/wireguard/`](./etc/wireguard)) — Túnel VPN para acceso remoto seguro al homelab.
- **Exporters de Prometheus** ([`opt/`](./opt)) — node_exporter + métricas específicas del gateway, scrapeadas desde Sauron.

## Filesystem espejado

- `opt/` — Stacks/scripts del gateway (vacío de momento).
- `etc/` — Reservado para `wireguard/wg0.conf` (no commiteado: contiene claves privadas).

## Referencias

Notas históricas sobre la configuración prevista en [`../obsidian/legacy-TFG/WireGuard — Instalación en Heimdall.md`](../obsidian/legacy-TFG/WireGuard%20%E2%80%94%20Instalaci%C3%B3n%20en%20Heimdall.md) y [`../obsidian/legacy-TFG/📊 Exporters de Prometheus — Heimdall.md`](../obsidian/legacy-TFG/%F0%9F%93%8A%20Exporters%20de%20Prometheus%20%E2%80%94%20Heimdall.md).

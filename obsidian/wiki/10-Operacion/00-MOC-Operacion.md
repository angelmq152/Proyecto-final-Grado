---
title: 10 · Operación — MOC
tags: [moc, operacion, cli, telegram, http]
---

# 🧑‍✈️ 10 · Operación — MOC

> [!abstract] Día a día con Lobster
> Tres superficies de operación: **CLI** (vía `uv run lobster …`), **HTTP** (endpoints administrativos) y **Telegram** (interactivo, con aprobaciones). Esta sección es la **guía operativa** del proyecto.

## Notas

- [[01-Comandos-CLI]] — todos los subcomandos de `lobster`.
- [[02-Comandos-Telegram]] — comandos en chat y texto libre.
- [[03-Endpoints-HTTP]] — `/health`, `/metrics`, `/webhook/alert`, `/admin/jobs`, `/admin/trigger`.
- [[04-Modos-normal-dryrun-paused]] — qué hace cada modo.
- [[05-Flujo-aprobacion-humano]] — qué ves en Telegram cuando llega una aprobación.
- [[06-Daily-summary-Obsidian]] — cómo se genera la nota diaria.
- [[07-Troubleshooting]] — síntomas y diagnóstico (incluye sección K3s: puerto zombie, kubeconfig, conflicto k3s-server/agent).
- [[08-Failover-y-recuperacion]] — cómo Lobster detecta la caída de matrix y migra cargas a fallback de forma autónoma.
- [[09-Postmortem-Failover-Kubeconfig-2026-05-23]] — postmortem: kubeconfig incorrecto + is_node_alive sin TCP probe bloqueaban el failover.

# Proyecto-final-Grado

TFG ASIR de Ángel Martín Quero — **homelab SaaSphere**: servicio ficticio de hosting web para pymes orquestado con inteligencia artificial local.

## Nodos del homelab

Cada nodo es una máquina física/virtual del homelab. Su carpeta replica el filesystem real (`opt/`, `etc/`), así la ruta en el repo coincide con la ruta en la máquina.

| Nodo | Rol | Servicios |
|------|-----|-----------|
| [`LeIA/`](./LeIA) | Agente IA orquestador | Lobster (FastAPI + aiogram) + Ollama (qwen3:8b / qwen3:32b) |
| [`Matrix/`](./Matrix) | Capa de orquestación | K3s + registry Docker |
| [`Sauron/`](./Sauron) | Observabilidad | Prometheus, Grafana, Loki, Alertmanager |
| [`Heimdall/`](./Heimdall) | Gateway / VPN | WireGuard + node exporters (planificado) |

## Cargas de trabajo

- [`tenants/`](./tenants) — Aplicaciones de los inquilinos (tenants) que el agente despliega y gestiona en K3s. Primer tenant: [`tenants/saasphere/`](./tenants/saasphere) — landing estática del propio proyecto.

## Documentación del TFG

- [`docs/memoria/`](./docs/memoria) — Memoria oficial (.docx, PDF) y plantilla del centro.
- [`docs/infra/topologia.md`](./docs/infra/topologia.md) — **Topología del homelab**: tabla de nodos, IPs, roles, diagrama ASCII de la LAN y política de secretos.
- [`docs/Glosario_TFG.html`](./docs/Glosario_TFG.html), [`docs/Revision_TFG_AngelMartinQuero.html`](./docs/Revision_TFG_AngelMartinQuero.html) — Material auxiliar.
- [`docs/versiones-anteriores/`](./docs/versiones-anteriores) — Borradores y backups del documento.
- [`obsidian/`](./obsidian) — Wiki técnica viva del proyecto (vault Obsidian).
- [`prompts-chat/`](./prompts-chat) — Prompts y contexto para chats IA.

## Quickstart — agente Lobster (nodo LeIA)

```bash
cd LeIA/opt/lobster
uv sync
uv run pytest
uv run lobster   # arranca FastAPI + Telegram bot
```

Comandos CLI más usados:

```bash
uv run lobster ask "prompt"          # one-shot
uv run lobster decisions list        # decisiones recientes del agente
uv run lobster actions list          # mutaciones aplicadas
uv run lobster state set paused      # pausa el agente
```

## Repos relacionados (legacy)

- `angelmq152/saasphere-openclaw` — historial completo del desarrollo del agente Lobster (origen).
- `angelmq152/Proyecto-TFG` — configs iniciales por nodo y notas históricas.

Ambos quedan congelados como respaldo. Este repo (`Proyecto-final-Grado`) es la nueva fuente única de verdad.

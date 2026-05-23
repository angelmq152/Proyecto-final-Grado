---
title: Topología del homelab SaaSphere
tags: [arquitectura, topologia, saasphere, homelab, k3s]
aliases: [Topología, SaaSphere homelab]
---

# 🖧 Topología del homelab SaaSphere

> [!abstract] La cara física del proyecto
> SaaSphere se reparte sobre 5 hosts físicos/virtuales. **LeIA** actúa como control-plane del clúster K3s y aloja el agente Lobster. **Matrix** y **fallback** son los nodos worker donde corren las cargas de trabajo de los tenants. Los otros dos hosts son infraestructura externa: Sauron (observabilidad) y Heimdall (edge/DNS).

## 🧭 Hosts y roles

| Host | IP | Rol | Servicios principales |
|---|---|---|---|
| **LeIA** | `192.168.1.200` | K3s control-plane + cerebro IA | Lobster (FastAPI :8080), Ollama (:11434), k3s server |
| **Sauron** | `192.168.1.201` | Observabilidad | Prometheus :9090, Alertmanager :9093, Loki :3100, Grafana |
| **Matrix** | `192.168.1.202` | K3s worker principal | k3s-agent, workloads de tenants |
| **Fallback** | (local) | K3s worker cold-standby | k3s-agent tainted `saasphere/role=fallback:NoSchedule` |
| **Heimdall** | (edge) | Proxy / DNS | Traefik / `*.saasphere.local` |

## 🗺️ Diagrama lógico

```mermaid
flowchart TB
    Internet((Internet))

    subgraph leia[LeIA · 192.168.1.200]
      OC[Lobster\nFastAPI :8080]
      OL[Ollama :11434\nqwen3:8b · qwen3:32b]
      DB[(SQLite\n/var/lib/lobster/state.db)]
      OBS[/Vault Obsidian\n/opt/lobster/obsidian/]
      OC --> OL
      OC --> DB
      OC --> OBS
    end

    subgraph sauron[Sauron · 192.168.1.201]
      PR[Prometheus :9090]
      LO[Loki :3100]
      AM[Alertmanager :9093]
      GR[Grafana]
    end

    subgraph leia_k3s[LeIA · k3s server]
      KS[K3s API server\n:6443]
    end

    subgraph matrix[Matrix · 192.168.1.202]
      KA[k3s-agent]
      TN[(Tenants\nnamespaces tenant-*)]
      KA --> TN
    end

    subgraph fallback[Fallback]
      KFW[k3s-agent tainted]
    end

    Heimdall[Heimdall edge\n*.saasphere.local]

    Internet --> Heimdall
    Heimdall --> matrix

    OC -->|kubeconfig\n:6443/tcp| KS
    KS -.->|controla| KA
    KS -.->|controla| KFW
    OC -->|GET /api/v1/query\nHTTP| PR
    OC -->|GET /loki/api/v1/query_range\nHTTP| LO
    OC -->|GET /api/v2/alerts\nHTTP| AM
    AM -->|POST /webhook/alert\nHTTP| OC

    matrix -.->|node-exporter scrape| PR
    matrix -.->|promtail push| LO
```

## 🛡️ Política K8s por nodo

> [!info] Política de pinning
> El nodo **fallback** lleva el taint `saasphere/role=fallback:NoSchedule`. Los pods NO se planifican ahí salvo que se haga `pin_deployment_to_node('fallback')`. Cuando matrix se recupera, `unpin_deployment_from_node` libera el deployment para que K8s vuelva a programarlo donde quiera.

> [!warning] Hosts que NO son nodos K3s schedulables
> Los hosts `sauron` y `heimdall` aparecen en métricas de Prometheus como **targets externos** (node-exporter). **No son nodos del clúster**. `leia` sí es un nodo del clúster (control-plane) pero lleva el taint `node-role.kubernetes.io/master:NoSchedule` — los workloads de tenants no aterrizan ahí. Si pides al agente que "muévalo a sauron" se negará: solo `matrix` y `fallback` son schedulables para cargas de tenant.

## 🔐 Acceso desde LeIA al clúster

- `K8sConfig.kubeconfig_path = "/etc/lobster/kubeconfig"` (default).
- Apunta a `https://192.168.1.200:6443` — la API K8s corre en LeIA (control-plane).
- Es un kubeconfig con verbos de lectura + patch para Deployments, ConfigMaps y recursos permitidos.
- → Ver [[../08-Infraestructura/05-RBAC-Kubeconfig]] para el detalle.

## 📍 Por qué esta distribución

> [!tip] Razones operativas
> - **GPU en LeIA, no en matrix** → matrix necesita CPU libre para tenants; la inferencia LLM va donde está la VRAM.
> - **Control-plane en LeIA** → cuando matrix cae como worker, la API K8s (en LeIA) sigue operativa. Lobster puede consultar el estado del clúster y actuar (pin_deployment_to_node, etc.) incluso durante la caída del worker.
> - **Observabilidad fuera del nodo monitorizado** → si matrix cae, Sauron sigue viendo y alertando.
> - **Edge separado** → certificados Let's Encrypt y DNS no se mezclan con K3s.
> - **SQLite local en LeIA, no en K8s** → el agente debe sobrevivir a una caída del clúster que está monitorizando.

→ Ver también [[../08-Infraestructura/03-Hosts-LeIA-Sauron-Heimdall]] para detalles por host.

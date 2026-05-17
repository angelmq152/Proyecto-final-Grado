---
title: Roadmap priorizado
tags: [mejoras, roadmap, priorizacion]
---

# 🗺️ Roadmap priorizado

> [!abstract] El orden importa
> Esta nota ordena **todas las mejoras** detectadas en cuatro olas. Cada ola asume que la anterior está hecha.

## 🚨 Ola 1 — Antes de la entrega del TFG (urgente)

> [!danger] Bloqueantes para la defensa académica
> Tienen que estar listos antes de imprimir/grabar la demo.

| # | Mejora | Tipo | Esfuerzo |
|---|---|---|---|
| 1 | **D-01** Rellenar Fase 10 "Demo y pruebas" del PDF | Doc | 4 h |
| 2 | **D-02** Rellenar Procedimientos de Control y Evaluación | Doc | 2 h |
| 3 | **D-03** Listar casos de prueba reales en PDF | Doc | 2 h |
| 4 | **D-04** Añadir Dificultades 2-7 al PDF | Doc | 2 h |
| 5 | **B-01..B-07** Corregir brechas en la wiki técnica | Wiki | 3 h |
| 6 | **B-07/T-30** Documentar dificultad CUDA en Troubleshooting | Wiki | 1 h |
| 7 | Unificar naming "Lobster" en PDF (quitar nemoclaw) | Doc | 1 h |
| 8 | Vídeo demo grabado (caso real onboarding) | Demo | 4 h |

**Total estimado Ola 1**: ~20 horas. **Casi todo es documentación/corrección.**

## 🟠 Ola 2 — Post-defensa (primer mes)

> [!warning] Operacionales para empezar a vender
> Si SaaSphere va a empezar a captar clientes, estos cubren huecos críticos.

| # | Mejora | Tipo | Esfuerzo |
|---|---|---|---|
| 9 | **N-01** Plantilla "Web con gestión de usuarios" Jinja2 | Código | 8 h |
| 10 | **T-01** Fallback LLM a Claude Haiku/Sonnet cuando Ollama falla | Código | 6 h |
| 11 | **T-02** Backup automático SQLite a S3 (rclone + cron) | Infra | 2 h |
| 12 | **T-21** Wake-on-request para tenants scale-to-zero | Código | 8 h |
| 13 | **N-02** CRM ligero (tablas `customers`, `subscriptions`) | Código | 6 h |
| 14 | **T-08** Auth Bearer en `/admin/*` y `/webhook/alert` | Código | 2 h |
| 15 | **T-23** Backup automatizado por tier (Velero o pg_dump) | Infra | 6 h |
| 16 | **T-31** `lobster doctor` para verificar health del stack | Código | 3 h |
| 17 | **N-04** Onboarding semiautomatizado por Telegram | Código | 8 h |
| 18 | **T-25** Dashboard Grafana ejecutivo (negocio) | Config | 4 h |
| 19 | **N-06** Solicitar Kit Digital (2000€) | Burocracia | 4 h |
| 20 | **T-10** NetworkPolicy default-deny en plantillas | Código | 3 h |

**Total estimado Ola 2**: ~60 horas. ~3 semanas a tiempo parcial.

## 🟡 Ola 3 — Crecimiento (mes 2-3)

> [!info] Para escalar de 5 a 25 clientes
> Cuando el modelo de negocio prueba funcionar.

| # | Mejora | Tipo | Esfuerzo |
|---|---|---|---|
| 21 | **T-12** Soporte multi-modelo runtime (Claude/OpenAI/Ollama) | Código | 12 h |
| 22 | **T-13** Métrica `lobster_llm_cost_eur_total` | Código | 4 h |
| 23 | **T-20** `change_tenant_tier` sin destruir | Código | 6 h |
| 24 | **T-22** Domain auto-provisioning (Cloudflare API) | Código | 8 h |
| 25 | **N-03** Facturación automática mensual (Holded API) | Código | 10 h |
| 26 | **N-05** Portal de cliente self-service | Código | 24 h |
| 27 | **T-26** Endpoint `/metrics/business` | Código | 2 h |
| 28 | **T-27** SLOs por nivel de soporte | Config | 4 h |
| 29 | **T-15** Streaming Ollama → Telegram | Código | 6 h |
| 30 | **T-09** TLS en registry Matrix:5000 | Infra | 3 h |
| 31 | **T-11** Sealed Secrets para tenants | Infra | 6 h |
| 32 | **T-28** CLI `lobster queue list|drop` | Código | 4 h |
| 33 | **N-09** Pipeline BI (export SQLite → S3) | Código | 6 h |
| 34 | **T-34** Tests E2E con kind | QA | 12 h |
| 35 | **N-07** Solicitar ENISA Jóvenes Emprendedores | Burocracia | 8 h |

**Total estimado Ola 3**: ~120 horas. ~5-6 semanas a tiempo parcial.

## 🟢 Ola 4 — Madurez (mes 4+)

> [!tip] Para llegar a 100+ clientes
> Mejoras estructurales que sostienen el escalado.

| # | Mejora | Tipo | Esfuerzo |
|---|---|---|---|
| 36 | **T-24** OpenTelemetry tracing | Código | 16 h |
| 37 | **T-03** Procedure de promoción Fallback → control-plane | Infra | 8 h |
| 38 | **T-16** Búsqueda vectorial en decisiones | Código | 12 h |
| 39 | **T-17** Detección de tool-calls como texto | Código | 4 h |
| 40 | **T-35** Modo `replay` para depurar incidencias | Código | 8 h |
| 41 | **T-06** Cifrar `state.db` en disco (SQLCipher) | Infra | 6 h |
| 42 | **N-08** Migración a GPU dedicada (cuando 25+ clientes) | Infra | 20 h |
| 43 | **N-10** Plantilla SLA contractual por tier | Doc | 4 h |
| 44 | **N-11** Plan de continuidad operador único | Doc | 4 h |
| 45 | **N-12** Marketing + landing saasphere.es | Producto | 16 h |
| 46 | **T-04** Watcher de Ollama (auto-restart) | Código | 4 h |
| 47 | **T-05** Alerta UDP de WireGuard | Config | 2 h |
| 48 | **T-19** Variantes de plantilla "user_app" (CRM, tienda, reservas) | Código | 24 h |
| 49 | **D-06** Anexos completos del PDF | Doc | 8 h |
| 50 | **T-29** `lobster tenants list --tier=premium` | Código | 2 h |
| 51 | **T-30** `lobster cost` informe | Código | 4 h |
| 52 | **T-32** Mejor gestión de `tool-requests` | Código | 4 h |
| 53 | **T-33** Refinar excepciones del watcher | Código | 2 h |
| 54 | **T-36** Migrar a aiogram v4 cuando esté estable | Código | 8 h |
| 55 | **T-18** Probar modelos cuantizados más pequeños | Código | 4 h |
| 56 | **T-14** Cache de respuestas LLM por hash de prompt | Código | 8 h |
| 57 | **T-07** Rotación tokens Telegram | Doc/Auto | 2 h |

**Total estimado Ola 4**: ~170 horas. Distribuible a lo largo del año.

## 📊 Resumen de esfuerzo

| Ola | Horas | Periodo sugerido |
|---|---|---|
| 1 — Antes TFG | 20 | Esta semana |
| 2 — Post-defensa | 60 | Mes 1 |
| 3 — Crecimiento | 120 | Mes 2-3 |
| 4 — Madurez | 170 | Mes 4-12 |
| **Total** | **370 h** | **~1 año** |

## 🎯 Mejoras "imprescindibles" si solo pudieras hacer 5

> [!danger] Top-5 absoluto
> 1. **D-01 + D-02 + D-04**: rellenar las secciones huérfanas del PDF.
> 2. **N-01**: plantilla "Web con gestión de usuarios" — sin esto no puedes vender el plan más rentable.
> 3. **T-01**: fallback LLM a cloud — sin esto, una caída de GPU mata el servicio.
> 4. **T-02**: backup SQLite a S3 — sin esto, una caída de disco mata la auditoría.
> 5. **N-04**: onboarding por Telegram — automatiza el alta de cliente y reduce CAC.

## 🚫 Lo que NO está priorizado (intencional)

- **HA / multi-clúster**: out of scope para TFG.
- **Multi-tenant fuerte (NetworkPolicy + isolated registries por cliente)**: hasta que haya conflicto real.
- **OAuth2 con keycloak para Telegram**: hoy un solo operador.
- **Soporte para Windows como SO host**: irrelevante.

## 🚏 Cómo seguir

> [!tip] Modo "ejecución"
> 1. Marcar este roadmap como **plan vivo**.
> 2. Hacer review mensual: avanzar items, mover entre olas si cambia el contexto.
> 3. Cada item completado → commit con tag `[improvement: T-XX]`.
> 4. Repasar tras los primeros 5 clientes reales: la Ola 3 puede acelerarse o retrasarse según problema real, no según especulación.

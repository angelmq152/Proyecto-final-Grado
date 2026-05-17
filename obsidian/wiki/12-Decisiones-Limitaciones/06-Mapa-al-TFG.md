---
title: Mapa al TFG
tags: [decisiones, tfg, mapa, academico]
---

# 🗺️ Mapa al TFG

> [!abstract] Cómo se mapea la wiki a las fases académicas
> Esta nota enlaza explícitamente cada capítulo de la wiki con la sección correspondiente del TFG. Pensado para el lector que viene desde el documento académico.

## 📚 Fases académicas (`obsidian/TFG_Fase*.md`)

| Fase | Archivo en `obsidian/` | Wiki — entrada equivalente |
|---|---|---|
| 1 — Bootstrap | (no escrito como TFG_Fase) | [[../01-Arquitectura/05-Modelo-evolutivo-por-fases#Fase 1]] |
| 2 — Reading | — | [[../03-Tools/00-MOC-Tools]] |
| 3 — Agente + policy | `docs/fase_3_cierre_validacion.md` | [[../02-Agente/05-Mutation-context]] |
| 4 — Aprobaciones | `docs/fase_4_aprobaciones.md`, `docs/fase_4_resumen_implementacion.md` | [[../02-Agente/06-Approval-manager]] |
| 5 — Mutaciones K8s | — | [[../03-Tools/06-Mutations-K8s]] |
| 6 — Scheduler + Watcher | `obsidian/TFG_Fase6_Lobster.md` | [[../07-Scheduler-Watcher/00-MOC-Scheduler]] |
| 7 — Observabilidad | `obsidian/TFG_Fase7_Lobster.md`, `docs/fase_7_*.md` | [[../06-Observabilidad/00-MOC-Observabilidad]] |
| 8 — Pin/unpin | `obsidian/TFG_Fase8_Lobster.md` | [[../03-Tools/08-Mutations-Nodes]] |
| 9 — Job queue | `obsidian/TFG_Fase9_Lobster.md` | [[../07-Scheduler-Watcher/07-Job-queue-fase9]] |

## 🧭 Mapa por capítulos típicos de memoria TFG

### Introducción

→ [[../01-Arquitectura/01-Vision-general]] + [[../01-Arquitectura/03-Topologia-homelab]]

### Estado del arte

→ [[../11-Modelos-IA/04-Pydantic-AI]] + [[../11-Modelos-IA/01-Qwen3-overview]]

### Análisis y diseño

→ [[01-Decisiones-arquitectura]] + [[../01-Arquitectura/02-Stack-tecnologico]]

### Implementación

→ Carpetas [[../02-Agente/00-MOC-Agente|02-Agente]], [[../03-Tools/00-MOC-Tools|03-Tools]], [[../04-Telegram/00-MOC-Telegram|04-Telegram]], [[../05-Persistencia/00-MOC-Persistencia|05-Persistencia]], [[../06-Observabilidad/00-MOC-Observabilidad|06-Observabilidad]], [[../07-Scheduler-Watcher/00-MOC-Scheduler|07-Scheduler-Watcher]]

### Despliegue

→ [[../08-Infraestructura/00-MOC-Infraestructura|08-Infraestructura]] + [[../08-Infraestructura/06-Systemd-deploy]]

### Resultados y evaluación

→ [[02-Limitaciones-actuales]] + [[../06-Observabilidad/02-Metricas-Prometheus]]

### Conclusiones y futuro

→ [[03-Trade-offs]] + [[04-Riesgos]] + [[05-Futuro-roadmap]]

### Anexos

→ [[../13-Glosario-Referencias/01-Glosario]] + [[../13-Glosario-Referencias/02-Cheatsheet-comandos]] + [[../13-Glosario-Referencias/03-Referencias-externas]]

## 📐 Aportaciones técnicas destacables

> [!tip] Lo que el TFG demuestra
> 1. **Un LLM local (Qwen3) puede operar infra K8s real** con un patrón agéntico tipado (Pydantic-AI).
> 2. **Doble defensa policy+RBAC** funciona como guardrail efectivo.
> 3. **Aprobaciones bloqueantes por Telegram** son una UX viable.
> 4. **Scheduler + Watcher + Webhook** cubren las tres latencias relevantes (5 min, real-time, alert-driven).
> 5. **La cola FIFO** resuelve la contención GPU en homelab consumer.
> 6. **El pin/unpin entre nodos** es un primer paso a la "elasticidad consciente del LLM".
> 7. **Daily summary en Obsidian** demuestra integración con el flujo de trabajo del operador.

## 📈 Métricas para evaluar

> [!example] Datos cuantitativos del TFG
> - Líneas de Python: ~5000.
> - Tests: 40+ archivos.
> - Tablas SQLite: 9.
> - Tools registradas: ~30.
> - Métricas Prom: 10+.
> - Reglas de alerta: 5.
> - Fases entregadas: 9.
> - Tenants reales gestionados: SaaSphere productivo.
> - Decisiones LLM/día: ~350-500.

## 🎓 Tribunal: dónde mirar primero

> [!tip] Recomendación de lectura
> 1. **Visión general** → [[../01-Arquitectura/01-Vision-general]] (5 min lectura).
> 2. **Topología** → [[../01-Arquitectura/03-Topologia-homelab]] (mapa físico).
> 3. **Bucle agéntico** → [[../01-Arquitectura/04-Flujo-datos-y-control]] (diagrama de secuencia).
> 4. **MutationContext** → [[../02-Agente/05-Mutation-context]] (la pieza central).
> 5. **Demo en vivo** → invocar `lobster ask "..."` desde LeIA.

---

→ Final del bloque académico. Cierra en [[../13-Glosario-Referencias/00-MOC-Glosario|Glosario]].

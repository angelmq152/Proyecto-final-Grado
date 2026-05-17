---
title: Limitaciones actuales
tags: [decisiones, limitaciones, tfg, academico]
---

# 🚧 Limitaciones actuales

> [!abstract] Lo que Lobster NO hace hoy
> Honestidad académica. Listamos las limitaciones reales del proyecto en su estado actual (Fase 9).

## 🧱 Limitaciones técnicas

### 1. Un solo clúster

Lobster opera **un único clúster** K3s. No hay soporte para multi-clúster, multi-region.

> [!info] No es un problema para SaaSphere
> El homelab no tiene multi-clúster. Pero esto descarta usos enterprise.

### 2. Dos nodos máximo

`pin_deployment_to_node` está restringido a `Literal["matrix", "fallback"]`. Añadir más nodos requiere:

- Modificar el `Literal`.
- Actualizar el system prompt.
- Actualizar la lógica de "matrix bajo presión" (que hoy solo mira matrix).

### 3. Sin alta disponibilidad

> [!warning] Una instancia, single point of failure
> Si LeIA cae, todo Lobster cae. No hay HA, no hay leader election. La cola está en RAM.

Mitigación: systemd `Restart=on-failure` cubre crashes; pero no hardware failures.

### 4. SQLite no escala horizontal

No se puede correr dos instancias de Lobster contra la misma SQLite (WAL no permite multi-writer).

## 🤖 Limitaciones del LLM

### 5. Latencia impredecible

→ Documentado en [[../11-Modelos-IA/07-Limitaciones-y-mitigaciones]].

p95 de qwen3:32b puede superar 8 min en runs complejos.

### 6. Tool calls inestables con think

→ Bug Qwen3 documentado. Solución: desactivar think en modos críticos.

### 7. Halucinación bajo presión

El LLM inventa nombres cuando recibe alertas urgentes. Los prompts mitigan pero no eliminan.

### 8. Reproducibilidad cero

Mismo prompt = respuestas distintas. Esto es inherente al medio.

## 🔁 Limitaciones funcionales

### 9. No hay `change_tenant_tier`

Cambiar un tenant de FREE a BASIC requiere borrar + redesplegar → pérdida de datos. **Falta una tool**.

### 10. No hay `wake-on-request`

Cuando un tenant está scaled-to-zero, no se "despierta" al recibir una request. El operador tiene que llamar `resume_tenant` manualmente.

### 11. No hay rollback de mutaciones

Si una mutación se aprueba y resulta dañina, no hay un "undo" automático. El operador tiene que aplicar el cambio inverso manualmente.

### 12. Sin trazabilidad cross-decision

Aunque `decisions` y `actions` tienen `decision_id` cruzado, no hay un visor de "esta decisión causó estas acciones causó este evento". Habría que escribir queries SQL manualmente.

## 🌐 Limitaciones operativas

### 13. Sin auth en `/admin/*`

Los endpoints `/admin/jobs` y `/admin/trigger` no piden token. Confían en LAN privada.

### 14. Sin backup automático de SQLite

`tests/test_alembic.py` valida el esquema, pero no hay backup programado de `state.db`. Si LeIA pierde el disco, todo el histórico se pierde.

### 15. Sin NetworkPolicy en tenants

→ Documentado en [[../09-Tenants/01-Modelo-multi-tenant#Aislamiento]]. Tenants pueden comunicarse entre sí.

### 16. Sin medición de coste real

No hay métrica de "$ por decisión". Como Ollama es local, el coste es eléctrico, no monetario.

## 📊 Limitaciones de observabilidad

### 17. Métricas Prom pero no traces

No hay OpenTelemetry traces. Hilos del flow (decision → tools → mutation → executor) se reconstruyen leyendo `decisions` + `actions` + logs Loki.

### 18. Logs no estructurados al 100%

Algunos `log.info("...")` siguen patrones consistentes pero no todos los eventos tienen `event=name k1=v1 k2=v2`. Loki ayuda con `| json` pero no es perfecto.

### 19. Dashboard solo en Grafana

No hay dashboard nativo en Obsidian / Telegram. `/status` da una vista, pero la versión rica requiere abrir Grafana.

## 🔮 Limitaciones de futuro

### 20. Solo TFG

Lobster está hecho para un homelab personal. Llevarlo a producción real requeriría:
- HA con leader election.
- Multi-tenant fuerte con NetworkPolicies.
- Audit log inmutable (no SQLite mutable).
- Roles diferenciados (no solo "operador único").
- Costing y rate-limiting.

→ Roadmap en [[05-Futuro-roadmap]].

## 🛑 Limitaciones que NO se van a resolver

> [!info] Lo que es deliberado
> - **Single-cluster**: el proyecto es educativo, no enterprise.
> - **Ollama local**: privacy by design.
> - **Telegram como UI**: simplicidad sobre flexibilidad.
> - **SQLite**: suficiente.
>
> Si quisiera evolucionar a producto, varias de estas decisiones cambiarían — pero como TFG demuestran lo que se quiere demostrar.

→ Sigue en [[03-Trade-offs]].

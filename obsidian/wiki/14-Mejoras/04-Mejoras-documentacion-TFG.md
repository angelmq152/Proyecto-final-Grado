---
title: Mejoras de documentación del TFG
tags: [mejoras, documentacion, tfg, academico]
---

# 📚 Mejoras de documentación del TFG

> [!abstract] Lo que el PDF deja sin cerrar
> El PDF tiene **secciones vacías o incompletas** que necesitan contenido antes de la entrega final. Esta nota las lista y propone redacción.

## 🚨 Secciones marcadas como **vacías o erróneas en el PDF**

### D-01 — Fase 10: Demo / Pruebas → "¡Error! Marcador no definido"

> [!danger] Crítica
> PDF página 5 (índice): *"j. Fase 10: Demo/pruebas ...... ¡Error! Marcador no definido."*
>
> Esta es la **demo final** del agente. **No existe** en el documento.

**Propuesta de contenido**:

```markdown
## Fase 10: Demo y pruebas finales

### Objetivo
Validar end-to-end el sistema completo con un cliente real.

### Caso de uso: alta de cliente "SaaSphere.es"
1. Petición vía Telegram en lenguaje natural.
2. Lobster razona el plan, solicita aprobación CRITICAL.
3. Aprobación humana.
4. Despliegue automático del tenant.
5. Verificación de salud.
6. Pause y resume vía Telegram.
7. Generación de daily_summary con el tenant operativo.

### Métricas obtenidas
- Tiempo de despliegue: X min.
- Tokens consumidos: X.
- Coste estimado: X €.
- Decisiones registradas: X.

### Vídeo demo
- Link YouTube + transcripción.
```

→ Mucho material visual ya existe en el PDF (capturas Telegram páginas 47-66).

### D-02 — Definición de Procedimientos de Control y Evaluación → VACÍO

> [!danger] Crítica
> PDF página 69: solo placeholder `<...>`.

**Propuesta de contenido**:

```markdown
## Definición de Procedimientos de Control y Evaluación

### Procedimiento de evaluación de incidencias

1. Detección
   - Por Alertmanager (alerta firing → webhook Lobster).
   - Por K8s Watcher (evento Warning crítico).
   - Por health_loop_read cada 5 min.
   - Por el operador (mensaje Telegram).

2. Clasificación
   - **P1 Critical** — servicio caído, cliente afectado → SLA según tier.
   - **P2 High** — degradación parcial.
   - **P3 Medium** — síntoma sin impacto.
   - **P4 Low** — observación.

3. Resolución
   - P1 ALERT_REACTIVE autónomo si confirmado.
   - P2-P3 esperan ciclo health_loop_analyze.
   - P4 registrado para revisión semanal.

4. Postmortem
   - Toda P1 → entry en `obsidian/postmortems/`.
   - Causa raíz · acción correctiva · prevención.

### Procedimiento de gestión de cambios

1. Cambios menores (versión patch)
   - Push directo a main + CI tests.
2. Cambios mayores (versión minor)
   - PR + review propia 24h.
3. Cambios de arquitectura (versión major)
   - ADR escrito en `obsidian/wiki/12-Decisiones-Limitaciones/`.
   - Merge en ventana de baja actividad.
```

### D-03 — Pruebas (Diseño del Proyecto) → solo plantilla genérica

PDF página 68: incluye solo los campos de plantilla. **Falta** la lista real de casos.

**Propuesta**: rellenar con los tests reales que existen en `tests/`. Mapear cada caso a su archivo:

| Caso de prueba | Archivo | Resultado |
|---|---|---|
| Decisión LLM se persiste correctamente | `test_orchestrator.py::test_run_persists_decision` | ✅ |
| Aprobación NORMAL bloquea hasta resolverse | `test_approval_manager.py::test_wait_for_decision` | ✅ |
| Policy rechaza kube-system | `test_policy.py::test_system_namespace_blocked` | ✅ |
| restart_pod autónomo en CrashLoop | `test_restart_pod.py::test_crashloop_autonomous` | ✅ |
| Webhook devuelve 202 inmediato | `test_webhook.py::test_alert_webhook_accepts` | ✅ |
| K8s Watcher reconecta | `test_k8s_watcher.py::test_reconnect_backoff` | ✅ |
| Memoria conversacional persiste | `test_conversation_memory.py::test_warm_up` | ✅ |
| Pin con tolerations | `test_node_pressure_tools.py::test_pin_with_tolerations` | ✅ |
| (40+ tests más) | | ✅ |

## 🟠 Secciones donde el PDF es muy breve y conviene ampliar

### D-04 — Mayores dificultades — solo "Dificultad 1"

PDF página 67 dice "Dificultad 1" pero **no hay Dificultad 2, 3...**. La sección queda coja.

**Propuestas de dificultades a añadir** (sacadas del propio histórico del proyecto):

- **Dificultad 2**: Bug Qwen3 emitiendo tool calls como texto en think mode. Detalles en [[../11-Modelos-IA/03-Think-mode]].
- **Dificultad 3**: Daily summary timeout 1200s insuficiente, ampliado a 1800s (commit fcedb6f).
- **Dificultad 4**: Falsos positivos de health_loop al buscar keywords en texto vs prefijo `[ANOMALÍA]` estricto.
- **Dificultad 5**: SQLite WAL contention al inicio (resuelto con session_maker dedicado para Decisions).
- **Dificultad 6**: aiogram v3 + lifespan FastAPI — sesiones HTTP compartidas (resuelto con `close_bot_session=False`).
- **Dificultad 7**: lightkube watch reconnect tras restart de K3s apiserver (resuelto con backoff exponencial).

### D-05 — Fuentes muy breves

PDF página 70 lista solo 10 fuentes (varias son Grafana / Prometheus genéricas). **Faltan**:

- Pydantic-AI docs.
- Qwen3 paper.
- Ollama docs.
- aiogram docs.
- lightkube github.
- K3s docs.
- Cert-manager docs.
- WireGuard whitepaper.
- Hetzner pricing.
- Stripe pricing.

Ya recogidas en [[../13-Glosario-Referencias/03-Referencias-externas]] de la wiki. Importarlas.

### D-06 — Anexos solo tienen guía de estilo

PDF página 71. **Añadir** anexos:

- A1 — Diagramas de arquitectura completos.
- A2 — Esquema SQL de las tablas.
- A3 — Lista completa de tools y su firma.
- A4 — Lista completa de métricas Prometheus.
- A5 — Reglas Prometheus en `lobster.rules.yaml`.
- A6 — Capturas Telegram (algunas ya están).
- A7 — Capturas Grafana.
- A8 — Snippets de manifiestos Jinja2 renderizados.

## 🟡 Sección "Resumen" del PDF — mejorable

PDF página 3 usa el nombre **"LeIA (Lobster)"** y a veces "Lobster". El proyecto debería decidir:

> [!warning] Inconsistencia de naming
> - PDF página 3: "agente de inteligencia artificial LeIA (Lobster)".
> - PDF página 7: "ollama y Lobster".
> - Código: `lobster`.
> - Repo GitHub: `saasphere-lobster`.
>
> **Propuesta**: unificar a **"Lobster"** (un solo nombre) corriendo en el nodo **LeIA**. Borrar referencias a "Lobster" del PDF.

## 📐 Estructura recomendada del PDF tras correcciones

```
1. Licencia · Resumen · Índices                        ← OK
2. Introducción                                         ← OK
3. Necesidades del Sector Productivo                    ← OK
4. Diseño del proyecto
   4.1 Requisitos y restricciones                       ← OK
   4.2 Decisiones de diseño                             ← OK (pero ampliar IA)
   4.3 Arquitectura                                     ← Corregir Heimdall/ESXi
   4.4 Modos de funcionamiento                          ← OK
5. Implementación
   5.1 Fase 1 - Hardware                                ← OK
   5.2 Fase 2 - Entorno virtual                         ← OK
   5.3 Fase 3 - VPN                                     ← OK
   5.4 Fase 4 - Monitorización                          ← OK
   5.5 Fase 5 - K3s                                     ← OK
   5.6 Fase 6 - Fallback                                ← OK
   5.7 Fase 7 - LeIA (Lobster)
       7.1 Esqueleto                                    ← OK
       7.2 Cliente Ollama                               ← OK
       7.3 Tools lectura                                ← OK
       7.4 Aprobación Telegram                          ← OK
       7.5 Tools                                        ← OK
       7.6 Triggers / scheduling                        ← OK
       7.7 Observabilidad                               ← OK
       7.8 SSH controlado                               ← Ampliar
       7.9 Hardening y resiliencia                      ← Ampliar
       7.10 Demo / pruebas                              ← D-01 RELLENAR
   5.8 Fase 8 - Cargas de trabajo (pin/unpin)           ← OK
   5.9 Fase 9 - Cola FIFO                               ← Añadir al PDF si no está
   5.10 Fase 10 - Pruebas generales                    ← OK
6. Mayores dificultades                                 ← D-04 AMPLIAR
7. Diseño del Proyecto / Pruebas                        ← D-03 RELLENAR
8. Procedimientos de Control y Evaluación               ← D-02 RELLENAR
9. Fuentes                                              ← D-05 AMPLIAR
10. Anexos                                              ← D-06 AMPLIAR
```

## 📋 Checklist de cierre del PDF

> [!example] Antes de imprimir / entregar
> - [ ] D-01 Rellenar Fase 10 (Demo y pruebas).
> - [ ] D-02 Rellenar Procedimientos de Control y Evaluación.
> - [ ] D-03 Listar casos de prueba reales mapeados a `tests/`.
> - [ ] D-04 Añadir Dificultades 2-7 (think mode, timeouts, etc.).
> - [ ] D-05 Ampliar fuentes a ~20-30 entradas.
> - [ ] D-06 Añadir anexos A1-A8.
> - [ ] Decidir naming: Lobster (no Lobster) y aplicar consistentemente.
> - [ ] Corregir Heimdall (es VPN, no edge proxy).
> - [ ] Añadir nodo ESXi al diagrama.
> - [ ] Añadir Fase 9 (cola FIFO) al cuerpo si falta.

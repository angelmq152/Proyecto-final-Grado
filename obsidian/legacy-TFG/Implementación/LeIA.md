# 🧠 Nodo LeIA — Plan de Implementación

> [!abstract] Resumen LeIA es el nodo de inteligencia artificial y automatización de SaaSphere. Ejecuta **OpenClaw** como agente principal, orquestando modelos locales mediante **Ollama** y modelos externos vía API. Toda acción destructiva o de producción requiere aprobación humana explícita por Telegram.

---

## 📦 Stack Tecnológico

|Componente|Tecnología|Descripción|
|---|---|---|
|Agente principal|OpenClaw|Daemon persistente con canal Telegram|
|Motor de inferencia|Ollama|Ejecución local de modelos LLM|
|Orquestación de flujos|n8n|Gestión del ciclo de vida de tareas|
|Observabilidad|Loki + Grafana|Audit log y visualización|
|Canal humano|Telegram|Aprobación de acciones críticas|

---

## 🖥️ Hardware del Nodo

> [!info] Especificaciones de LeIA
> 
> - **CPU:** Intel Core i9-12900KF
> - **RAM:** 32 GB
> - **GPU:** NVIDIA RTX 3060 Ti — _8 GB VRAM_
> - **Rol:** IA local, análisis, automatización, toma de decisiones

> [!warning] Limitación crítica de VRAM La RTX 3060 Ti dispone de **8 GB de VRAM**. Modelos como Gemma 27B Q4 requieren ~15-18 GB. La ejecución de modelos pesados se hará sobre **CPU + RAM**, asumiendo latencia elevada. Para tareas críticas con alta exigencia de razonamiento se usará **API externa** (Claude / OpenAI).

---

## 🤖 Gestión de Modelos

OpenClaw selecciona el modelo en función de la complejidad de la tarea:

```
Tarea sencilla   →  Modelo ligero   (llama3.1:8b   — cabe en VRAM)
Tarea compleja   →  Modelo pesado   (gemma2:27b-q4 — CPU/RAM, lento)
Tarea crítica    →  API externa     (claude-sonnet-4-5 — pago por token)
```

### Asignación por tipo de tarea

|Tarea|Modelo|Motivo|
|---|---|---|
|Análisis inicial de logs|`llama3.1:8b`|Rápido, bajo coste, cabe en GPU|
|Detección de errores críticos|`llama3.1:8b`|Latencia mínima, runs cada 5 min|
|Elaboración de informes diarios|`gemma2:27b-q4`|Necesita mayor razonamiento|
|Copias de seguridad con verificación|`gemma2:27b-q4`|Tarea compleja, se ejecuta de noche|
|Puesta en producción de cliente|`claude-sonnet-4-5` (API)|Máxima fiabilidad, aprobación humana previa|

---

## ⏱️ Planificación de Tareas

> [!tip] Filosofía de acceso OpenClaw **no tiene acceso permanente** a todos los sistemas. Los permisos se elevan por **skill activo**, no por ventana de tiempo. Cuando la tarea finaliza, el skill cierra su propio acceso. La configuración base en `openclaw.json` define los límites máximos absolutos.

### Tareas programadas

```
Cada 5 minutos  →  Lectura y análisis de logs en busca de errores críticos
Cada hora       →  Revisión de métricas de Prometheus / estado del clúster
Cada noche      →  Informe diario completo + copia de seguridad verificada
Bajo demanda    →  Puesta en producción (requiere orden humana por Telegram)
```

### Configuración de permisos base (openclaw.json)

```json
{
  "tools": {
    "allow": ["fs_read", "shell_read", "web_fetch"],
    "deny":  ["fs_write", "fs_delete", "shell_exec"]
  }
}
```

Los skills de tareas específicas elevan permisos temporalmente durante su propia ejecución y los cierran al terminar.

---

## 🔒 Seguridad y Control

> [!danger] Riesgo: Prompt Injection OpenClaw lee contenido externo (logs, webs, documentos). Un atacante puede embeber instrucciones maliciosas en esos datos para redirigir las acciones del agente. Este vector ya ha sido explotado en entornos reales.
> 
> **Mitigación:** No dar permisos de escritura/ejecución en el perfil base. Todo skill que requiera acción real debe estar explícitamente definido y ser auditado.

> [!success] Aprobación humana obligatoria Cualquier acción de **puesta en producción** debe ser ordenada explícitamente por un humano vía Telegram. OpenClaw verifica el **sender ID** del mensaje antes de ejecutar. Ningún proceso interno puede suplantar esta orden.

### Flujo de aprobación de deploy

```
Humano envía mensaje por Telegram
        ↓
OpenClaw verifica sender ID (solo IDs autorizados en config)
        ↓
Selecciona skill de deploy + modelo claude-sonnet-4-5
        ↓
Ejecuta despliegue en Matrix vía k3s
        ↓
Registra resultado en Loki
        ↓
Responde al humano con resultado por Telegram
```

---

## 📋 Audit Log

> [!note] Estrategia de logging No se necesita base de datos adicional. OpenClaw envía un JSON estructurado a **Loki** (ya desplegado en Sauron) al finalizar cada tarea. Grafana visualiza el historial automáticamente.

### Estructura del log por tarea

```json
{
  "timestamp": "2026-04-02T03:15:00Z",
  "task":          "analisis_logs",
  "model_used":    "llama3.1:8b",
  "input_summary": "logs nginx últimos 5 minutos",
  "output_summary":"2 errores 404, 1 error 500 en cliente-X",
  "action_taken":  "alerta enviada por Telegram",
  "tokens_used":   1240,
  "status":        "ok"
}
```

Cada registro incluye: **qué tarea**, **qué modelo decidió**, **con qué contexto**, **qué acción tomó** y **si fue exitosa**. Esto permite depurar cualquier incidente post-mortem.

---

## 🔄 Integración con el resto de la infraestructura

```
LeIA (OpenClaw + Ollama)
    │
    ├──[lectura]──→  Sauron (Prometheus / Loki / Grafana)
    ├──[lectura]──→  Matrix (logs de contenedores k3s)
    ├──[alertas]──→  Telegram (canal humano)
    ├──[deploy]───→  Matrix (k3s API — solo con aprobación)
    └──[audit]────→  Loki (registro de todas las acciones)
```

LeIA **nunca escribe directamente** en los sistemas de clientes. Toda acción sobre producción pasa por la API de k3s en Matrix, con el audit trail correspondiente en Loki.

---

## ⚠️ Restricciones y Pendientes

> [!warning] Pendiente de resolución
> 
> - **VRAM insuficiente para modelos pesados en local.** Definir política clara: ¿cuándo se acepta la latencia de CPU y cuándo se paga API externa?
> - **Canal Telegram:** configurar whitelist de sender IDs antes de conectar OpenClaw a producción.
> - **Skills de OpenClaw:** cada tarea necesita su propio SKILL.md definido. No improvisar permisos en caliente.
> - **Prueba de prompt injection:** antes de puesta en producción, simular un log con instrucciones maliciosas y verificar que el agente no las ejecuta.

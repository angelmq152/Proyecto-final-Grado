---
title: Operación — Daily summary en Obsidian
tags: [operacion, daily-summary, obsidian, vault]
---

# 📔 Daily summary → Obsidian vault

> [!abstract] Un informe diario en tu vault
> Cada día a las 08:00 (configurable) Lobster genera un informe operativo completo en Markdown y lo guarda en `obsidian/YYYY-MM/YYYY-MM-DD_daily_summary.md`. El operador lo abre en Obsidian igual que cualquier otra nota.

## 📂 Ubicación de los archivos

```text
obsidian/
├── 2026-05/
│   ├── 2026-05-14_daily_summary.md
│   ├── 2026-05-15_daily_summary.md
│   └── 2026-05-16_daily_summary.md
├── TFG_Fase6_Lobster.md
├── TFG_Fase7_Lobster.md
├── TFG_Fase8_Lobster.md
└── TFG_Fase9_Lobster.md
```

> [!info] El path es configurable
> ```toml
> [scheduler]
> obsidian_path = "/opt/lobster/obsidian"
> ```

## 🎨 Estructura del archivo

```markdown
---
date: 2026-05-16
time: 08:00
type: daily_summary
tags: [lobster, daily_summary]
---

# 2026-05-16 — Daily Summary

*Generado automáticamente por Lobster a las 08:00*

# Resumen diario

## 🖥️ Nodos
(tabla generada por el LLM con CPU/mem/estado)

## 🏢 Tenants y pods
(estado por namespace)

## ⚠️ Pods problemáticos
(o "Ninguno")

## 🚨 Alertas activas
(o "Ninguna")

## 🪵 Errores en logs (últimas 24 h)
(top errores de Loki)

## 📋 Decisiones del día
(top decisiones del agente)

## ✅ Conclusión
(estado general y recomendaciones)
```

## 🚀 Generación

> [!info] Job `daily_summary`
> - Cron: `0 8 * * *` (Europe/Madrid).
> - Modelo: `qwen3:32b`, **sin think**.
> - Timeout: 1800 s (30 min).
> - Tools: meta + prometheus + loki + k8s_basic + alertmanager + memory.

## 📝 Append vs new

```python
mode = "a" if note_path.exists() else "w"
```

> [!tip] Append-only
> Si por accidente se dispara dos veces en el mismo día (CLI `/admin/trigger/daily_summary`), se añade al final con separador:
> ```markdown
> ---
>
> *Actualización a las HH:MM*
> (segunda generación)
> ```

## 🔍 Cómo se ve en Obsidian

> [!info] Visualización
> Obsidian abre el archivo y renderiza:
> - Frontmatter como propiedades (graph view filter `type:daily_summary`).
> - Tags clickables.
> - Tablas Markdown con bordes.
> - Emojis como UTF-8.

## 🎯 Cómo aprovecharlo

> [!tip] Consultas dataview (si el plugin está instalado)
> ```dataview
> TABLE date as "Fecha", file.name as "Nota"
> FROM "obsidian"
> WHERE type = "daily_summary"
> SORT date desc
> LIMIT 30
> ```

> [!tip] Búsqueda full-text
> Obsidian indexa todos los daily summaries. Ctrl+Shift+F → "wordpress crashloop" → encuentras todos los días donde hubo un problema con WordPress.

## ⚠️ Posibles errores

| Síntoma | Causa probable |
|---|---|
| El archivo no existe | qwen3:32b no terminó en 1800s (mira `lobster_scheduler_runs_total{outcome="timeout"}`) |
| Archivo existe pero solo frontmatter | El LLM devolvió cadena vacía o la tarea falló — revisa `decisions` |
| Contenido con "???" o placeholder | El LLM no usó tools — bug que el prompt ya intenta prevenir |
| Mensaje Telegram pero no archivo | OSError de I/O — revisa permisos en `obsidian/` |

> [!info] OSError no es fatal
> En `scheduler.py:_run_scheduled_job` el guardado de Obsidian va en try/except: si falla, incrementa `lobster_errors_total{component="scheduler", severity="warning"}` pero el job sigue como exitoso.

## 🤝 Convivencia con otras notas

> [!warning] No tocar manualmente
> Si añades contenido manualmente a un daily summary, y el job se vuelve a disparar (poco probable), el append lo conservará. Pero si en el futuro se cambia el flujo a "rewrite", se perderá. **Para anotaciones personales sobre el día, mejor crear una nota aparte.**

→ Ver detalle técnico en [[../07-Scheduler-Watcher/03-Global-state-Summary-Daily#daily_summary]].

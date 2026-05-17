---
title: 14 · Mejoras — MOC
tags: [moc, mejoras, roadmap, tfg]
aliases: [Mejoras MOC]
---

# 🛠️ 14 · Mejoras — MOC

> [!abstract] ¿De dónde sale esta sección?
> Apartado generado **tras leer la memoria TFG en PDF** (`AngelMartinQuero.pdf`, 71 páginas). El documento académico aportó contexto que no estaba ni en el código ni en los Markdown de fases: **modelo de negocio, análisis de competencia, costes reales, dificultades técnicas reales, decisiones estratégicas y datos de hardware específicos**.
>
> Esta sección consolida **todas las mejoras detectadas** comparando el PDF con el estado actual del código y de la wiki, agrupadas por dominio y priorizadas.

> [!warning] Brechas reales encontradas
> Algunas notas anteriores de la wiki **están incorrectas o incompletas** respecto al PDF. Las brechas se detallan en [[01-Brechas-detectadas-PDF]] — eso es lo primero que conviene corregir antes de hablar de mejoras futuras.

## 🗂️ Notas

- [[01-Brechas-detectadas-PDF]] — discrepancias entre la wiki/código y el PDF. **Leer primero**.
- [[02-Mejoras-tecnicas]] — propuestas técnicas (resiliencia, seguridad, performance).
- [[03-Mejoras-negocio-y-producto]] — modelo de ventas, ayudas, escalado.
- [[04-Mejoras-documentacion-TFG]] — partes vacías o incompletas del PDF a cubrir.
- [[05-Roadmap-priorizado]] — qué primero, qué después.

## 📊 Resumen ejecutivo

| Categoría | Críticas | Importantes | Deseables |
|---|---|---|---|
| Brechas wiki/código vs PDF | 7 | 4 | 2 |
| Técnicas (infra, IA, código) | 5 | 9 | 12 |
| Negocio y producto | 1 | 5 | 6 |
| Documentación TFG | 3 | 4 | 3 |
| **Total** | **16** | **22** | **23** |

→ Total identificado: **~61 mejoras**. El roadmap priorizado en [[05-Roadmap-priorizado]] organiza la ejecución.

## 🎯 Hilos transversales

> [!tip] Cuatro hilos atraviesan todas las mejoras
> 1. **Realismo del homelab**: el hardware actual no es de producción (R-01 a R-05 en el PDF). Muchas mejoras pasan por aceptar esto y planificar migración.
> 2. **Dual local/cloud LLM**: el PDF contempla APIs externas (GPT-5.5, Claude Opus 4.7…) como respaldo. Lobster hoy no las soporta.
> 3. **Modelo SaaS comercial**: el PDF define 9 packs comerciales con precios reales. La wiki técnica no refleja este nivel de servicio.
> 4. **Documentación TFG**: hay 3 secciones del PDF marcadas como **vacías o "Error! Marcador no definido"** que requieren cierre académico.

## 🚨 Las 5 mejoras más urgentes

> [!danger] Top-5
> 1. **Corregir la wiki técnica** (Heimdall, hardware, IPs) → [[01-Brechas-detectadas-PDF]].
> 2. **Documentar Fase 10 - Demo/Pruebas** (marcada como Error en el PDF) → [[04-Mejoras-documentacion-TFG#Fase 10]].
> 3. **Cerrar "Definición de Procedimientos de Control y Evaluación"** (sección vacía en PDF) → [[04-Mejoras-documentacion-TFG#Procedimientos]].
> 4. **Implementar fallback a API externa** cuando Ollama local falle → [[02-Mejoras-tecnicas#Fallback LLM externo]].
> 5. **Plantilla "Web con gestión de usuarios"** del modelo comercial — no existe Jinja2 para ella → [[03-Mejoras-negocio-y-producto#Plantilla usuarios]].

→ Resto del top-20 en [[05-Roadmap-priorizado]].

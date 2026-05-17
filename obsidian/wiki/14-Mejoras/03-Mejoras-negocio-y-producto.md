---
title: Mejoras de negocio y producto
tags: [mejoras, negocio, producto, tfg]
---

# 💼 Mejoras de negocio y producto

> [!abstract] El PDF describe un negocio, la wiki solo el código
> El TFG dedica las páginas 8-15 al **modelo de negocio**: análisis de mercado, competencia, productos comerciales, niveles de soporte, costes, rentabilidad y ayudas/subvenciones. Nada de esto está en la wiki técnica. Esta nota recoge **mejoras que alinean la implementación con el modelo comercial**.

## 🏪 Catálogo comercial (del PDF)

### Los 3 productos

| Producto | Descripción (PDF página 12) | Plantilla actual |
|---|---|---|
| **Landing Page** | Web estática 1 sola página · dominio · SSL · formulario · responsive | ✅ `static_site.yaml.j2` |
| **Web Corporativa** | Multi-página · CMS · galería · múltiples formularios · frontend completo | ⚠️ Parcialmente cubierto por `web_app.yaml.j2` |
| **Web con gestión de usuarios** | Registro/login · área privada · gestión por perfil · tienda / reservas (con coste extra CRM) | ❌ **No existe plantilla** |

### Los 3 niveles de soporte

| Nivel | Descripción (PDF página 12) |
|---|---|
| **Basic** | Monitorización automática · alertas · reinicio automático. **Sin intervención humana**. |
| **Standard** | Lo anterior + respuesta < 4h en horario laboral · 3 cambios menores incluidos. |
| **Premium 24/7** | Lo anterior + respuesta fuera horario · cambios menores ilimitados · informes mensuales · reunión trimestral. |

### Tabla de precios (€/mes, PDF página 12)

| Producto | Basic | Standard | Premium |
|---|---|---|---|
| Landing Page | 59 | 89 | 129 |
| Web Corporativa | 99 | 149 | 199 |
| Web con usuarios | 179 | 249 | 349 |

## 💰 Mejoras de negocio identificadas

### N-01 — Implementar la plantilla "Web con gestión de usuarios"

> [!danger] Crítica para el modelo comercial
> El producto **más rentable** del PDF (349€/mes premium) **no tiene plantilla técnica**. Imposible vender lo que no se puede desplegar.

**Propuesta**:
- Crear `lobster_agent/manifests/user_app.yaml.j2`.
- Stack sugerido: imagen custom + PostgreSQL + Redis (sesiones) + Ingress + PVCs.
- Variables Jinja2: `name, tier, hostname, image, port, env, admin_email, db_size, redis_size`.
- Auto-generar contraseñas (igual que wordpress).

### N-02 — Modelo de datos del cliente (CRM ligero)

> [!warning] Importante
> El PDF (página 12) menciona *"con coste extra por conexión con CRM"*. Hoy no hay nada para **gestionar clientes**.

**Propuesta**:
- Tabla SQLite `customers` con: id, nombre, email, dominio, tier, producto, fecha_alta, fecha_baja.
- Tabla `subscriptions` con histórico de cambios de tier.
- CLI `lobster customers list|show|create|update`.
- Comando Telegram `/clientes` para vista rápida.

### N-03 — Facturación automática mensual

PDF página 11 menciona modelo 037, IVA, IRPF, modelo 347, facturación. **Propuesta**:
- Integración con Holded / FacturaDirecta / FacturaScripts via API.
- Job mensual `billing` que genera factura por cliente activo.
- Métrica `lobster_invoices_emitted_total`.

### N-04 — Onboarding semiautomatizado por Telegram

PDF página 47 muestra que el operador despliega tenants a mano. **Propuesta**:
- Comando `/onboard <email>` que inicia un flujo paso a paso:
  1. ¿Qué producto? (3 opciones)
  2. ¿Qué tier? (3 opciones)
  3. Dominio (validación DNS)
  4. Pago (link Stripe/Holded)
  5. Despliegue automático tras pago confirmado.

### N-05 — Portal de cliente self-service

PDF página 12 promete *"valoración frontend completa para el cliente, adaptada a sus necesidades"*. **Propuesta**:
- Web portal en `cliente.saasphere.es` donde el cliente:
  - Ve estado de su tenant (uptime, requests).
  - Descarga sus backups.
  - Pide cambios (genera ticket → Telegram al operador).
  - Cambia su contraseña.

### N-06 — Solicitar Kit Digital (subvención 2000€)

PDF página 15. **Acción operativa** no técnica, pero documentable:
- Crear `docs/business/kit_digital_solicitud.md` con pasos.
- Aprovechar para invertir en herramientas BI (Power BI / Fabric / Looker Studio).

### N-07 — Solicitar ENISA Jóvenes Emprendedores (25-75k€)

PDF página 15. Similar. La cifra mayor permitiría comprar **GPU dedicada** y dejar de depender de la RTX 3060 Ti.

### N-08 — Modelo dual: local + cloud para escalar

> [!tip] Ya tocado en [[02-Mejoras-tecnicas#T-01]]
> PDF: *"Por lo tanto, podremos mantener este modelo hasta que tengamos la estabilidad económica como para comprar nuestros propios servidores de Inteligencia Artificial."*

**Propuesta operativa**:
- Hasta 9 clientes: 100% Ollama local.
- 10-25 clientes: Cloud fallback opcional para `daily_summary` (más calidad).
- 25+ clientes: Migración a GPU dedicada en VPS Hetzner GEX44.

### N-09 — Analytics de adopción

PDF página 15 menciona usar Fabric (Microsoft) para BI. **Propuesta**:
- Exportar diariamente datos de SQLite a CSV/Parquet en S3.
- Cuadros: tasa de éxito de aprobaciones, latencia LLM por modelo, churn por tier, tickets resueltos por nivel de soporte.

### N-10 — SLA contractual escrito por nivel

PDF promete tiempos de respuesta. **Propuesta**:
- Plantilla LaTeX/Markdown con contrato SLA para cada nivel.
- Almacenado en `docs/business/sla/`.
- Versionado en git para auditoría legal.

### N-11 — Plan de continuidad ante baja del operador único

PDF página 10 lista como desventaja: *"Equipo unipersonal al inicio"*. **Propuesta**:
- Documentar runbook para que un sustituto pueda operar 1 semana.
- Almacenar credenciales en gestor con acceso de emergencia (Bitwarden Emergency Access).

### N-12 — Marketing y captación

PDF página 9 analiza la competencia (La Teva web, Apiumhub, Tallium INC). **Propuesta**:
- Crear landing en `saasphere.es` (que es… un tenant SaaSphere — meta).
- SEO básico para "página web autónomo barato".
- Comparativa explícita con la competencia.

## 🎯 Producto: features faltantes según el PDF

| Feature mencionada | Estado actual | Mejora |
|---|---|---|
| Dominio incluido | ❌ Cliente lo trae | T-22 (auto-provisioning) |
| SSL automático | ✅ Traefik + Let's Encrypt | OK |
| Formulario de contacto | ❌ No template | Añadir a static_site |
| CMS sencillo | ⚠️ Wordpress | Considerar Decap CMS / Strapi para corporativas |
| Múltiples formularios | ❌ | Plantilla con Formspree / NocoDB |
| Galería | ❌ | Subir como assets en PVC |
| Área privada | ❌ | N-01 |
| Tienda online | ❌ | Variante de N-01 con WooCommerce |
| Gestión de reservas | ❌ | Variante de N-01 con Cal.com |
| CRM | ❌ | Integración EspoCRM / SuiteCRM |
| Informes mensuales | ❌ | Auto-generar PDF con metrics por cliente |
| Reunión trimestral | ❌ | Calendly + plantilla agenda |

## 📈 KPIs de negocio a tracker

> [!example] Métricas que la wiki debería exponer
> - **MRR** = Σ precio_tier × tenants_activos.
> - **ARR** = MRR × 12.
> - **Margen bruto %** = (Ingresos − costes_variables) / Ingresos.
> - **CAC** = coste captación / clientes nuevos.
> - **Churn rate %** = bajas / activos.
> - **LTV** = ARR_medio_cliente × años_promedio.
> - **Coste por decisión IA** = (€ Ollama + € cloud LLM) / decisiones totales.

## 🚏 Sigue en…

→ [[04-Mejoras-documentacion-TFG]] para las partes del PDF que están vacías.
→ [[05-Roadmap-priorizado]] para priorización.

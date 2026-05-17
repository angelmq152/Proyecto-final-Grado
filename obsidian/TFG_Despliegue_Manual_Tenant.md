# Despliegue manual de un tenant via Telegram

## ¿Qué demuestra este capítulo?

> [!abstract] Resumen ejecutivo
> Este capítulo documenta el **primer despliegue real** de un cliente sobre la plataforma SaaSphere, ejecutado de extremo a extremo a través de Lobster y Telegram. El tenant desplegado (`saasphere`, accesible en `http://saasphere.saasphere.local`) es un sitio estático servido por nginx que aloja la landing del propio proyecto.
>
> El despliegue no se hace con `kubectl apply` ni con un script local. Se hace **conversando con el bot**: Angel manda un mensaje en lenguaje natural describiendo el tenant, el LLM extrae los parámetros y llama a la tool `deploy_tenant`, la policy valida los recursos, el `ApprovalManager` exige aprobación humana CRITICAL via inline keyboard y, tras el click, los manifests se aplican contra el cluster K3s. Para sitios estáticos, Lobster devuelve la ruta física del PVC en el nodo, donde el operador sube el contenido por `scp`.
>
> El valor para el TFG está en demostrar que el flujo conversacional + policy + aprobación humana funciona end-to-end, y en documentar las **tres fricciones reales** detectadas durante la ejecución, con sus mitigaciones inmediatas y propuestas de mejora.

> [!note] Tecnologías utilizadas
> `aiogram` v3 · `pydantic-ai` · `Qwen3:8b` (Ollama) · `Jinja2` · `lightkube` · `K3s` · `Traefik` · `local-path-provisioner` · `SQLModel` · `Typer` · `OpenSSH`

---

## Tenant elegido

> [!tip] Explicación para el TFG
> El sitio fuente es `~/futuraweb` en LeIA: tres archivos (HTML + 1 PNG, 2,2 MB en total). El `index.html` es un simple `<meta http-equiv="refresh">` que redirige a `SaaSphere.html`, lo que permite usar la imagen `nginx:alpine` por defecto del template — `nginx` sirve `index.html` automáticamente y el navegador completa el redirect. No hace falta `nginx.conf` custom ni construir una imagen Docker propia.

> [!example] Inventario del sitio fuente
> ```bash
> $ ls -la ~/futuraweb/
> -rw-rw-r-- 1 angel angel     101 may 15 15:30 index.html        # meta-refresh a SaaSphere.html
> -rw-rw-r-- 1 angel angel   86782 may 15 15:32 SaaSphere.html   # landing real
> -rw-rw-r-- 1 angel angel 2148308 may 15 15:36 SaaSphere-logo.png
> ```

---

## Despliegue ejecutado

### 1. Conversación natural con el bot

> [!tip] Explicación para el TFG
> El handler `handle_free_text` (`lobster_agent/telegram/handlers.py:317`) intercepta cualquier mensaje de texto que no empiece por `/` y lo despacha al agente como `CaseUse.CHAT`. El LLM (`qwen3:8b`) recibe el texto, decide qué tool llamar y extrae sus argumentos a partir del lenguaje natural. No hay parser ni esquema fijo de comandos: la "API" del operador es el español.

> [!example] Texto enviado al bot
> ```
> Despliega un tenant nuevo de tipo static_site llamado saasphere,
> tier free, owner angel.
> ```
>
> Invocación de tool resultante (visible en `decisions list`):
> ```python
> deploy_tenant(
>     tenant_type="static_site",
>     name="saasphere",
>     tier="free",
>     owner="angel",
> )
> ```
>
> El parámetro `hostname` se omite a propósito — `deploy_tenant` (`lobster_agent/agent/tools/mutations/tenant.py:60`) lo deriva como `<name>.saasphere.local` por defecto, dando `saasphere.saasphere.local`.

---

### 2. Validación del nombre (DNS-1123)

> [!tip] Explicación para el TFG
> El nombre del tenant es **al mismo tiempo** el nombre del namespace en Kubernetes y el prefijo de todos los recursos derivados (Deployment, Service, Ingress, PVC). Kubernetes exige que ese identificador sea un *label* DNS-1123, lo que descarta cualquier nombre con puntos. El intento inicial — llamarlo directamente `saasphere.es` — fue rechazado en `tenant.py:48`. El `hostname` es un campo independiente y sí acepta puntos porque es un FQDN destinado al ingress.

> [!example] Regex de validación y respuesta del agente al primer intento
> ```python
> # lobster_agent/agent/tools/mutations/tenant.py:16
> DNS_1123_LABEL = re.compile(r"^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$")
> ```
>
> Mensaje devuelto por la tool si `name="saasphere.es"`:
> ```
> deploy_tenant failed before action creation: name must be a DNS-1123 label
> ```
>
> Solución adoptada: `name="saasphere"` (interno), `hostname` derivado `saasphere.saasphere.local` (público en LAN). Mantener `saasphere.es` como dominio público se deja para una fase posterior con cert-manager + DNS público.

---

### 3. Aprobación CRITICAL vía Telegram

> [!tip] Explicación para el TFG
> `deploy_tenant` lleva `severity_override=ActionSeverity.CRITICAL` hardcoded en `tenant.py:123`. La razón es deliberada: crear un tenant no es destructivo, pero es **irreversible-light** (genera namespace + PVC + cuotas + ingress que potencialmente expone red al exterior), así que la policy exige aprobación humana explícita sin excepción. El `ApprovalManager` formatea el mensaje con `format_approval_request` (`lobster_agent/telegram/messages.py:46`), publica los botones del `approval_keyboard` y bloquea la ejecución hasta que Angel pulsa uno. CRITICAL usa timeout de 3600 s (`ApprovalConfig.critical_timeout_seconds`) y reenvía recordatorios cada 60 s (`critical_reminder_interval_seconds`) — diseñado para no perder el evento aunque Angel esté lejos del móvil.

> [!example] Mensaje literal recibido en Telegram
> ```
> 🔔 Solicitud de aprobación 🚨
>
> ⚡ Acción: deploy_tenant
> 🏷️ Caso de uso: chat
> 🏠 Tenant: saasphere
>
> 📋 Detalle:
> {
>   "hostname": "saasphere.saasphere.local",
>   "name": "saasphere",
>   "namespace_labels": {
>     "saasphere": {
>       "saasphere.io/owner": "angel",
>       "saasphere.io/tenant": "true",
>       "saasphere.io/tier": "free",
>       "saasphere.io/type": "static_site"
>     }
>   },
>   "owner": "angel",
>   "resource_count": 6,
>   "tenant_type": "static_site",
>   "tier": "free"
> }
>
> ⏰ Caduca: 2026-05-16T18:00:00+00:00 (60 min)
> 🆔 2462cd8c
> ```
>
> Botones (`lobster_agent/telegram/keyboards.py:4`): `[Aprobar] [Rechazar]` en una fila y `[Pausar todo]` en la siguiente, con `callback_data` `approve:<id>` / `reject:<id>` / `pause_all`.
>
> *(Captura manual del Telegram — incluir el screenshot del mensaje + botones al insertar el capítulo en el TFG.)*

---

### 4. Aplicación de manifests y obtención del `host_path`

> [!tip] Explicación para el TFG
> Tras el click en `Aprobar`, el `executor` interno de `deploy_tenant` aplica los recursos del manifest renderizado en orden de dependencia (`_dependency_order` en `tenant.py:303`): `Namespace → PVC → ResourceQuota → Deployment → Service → Ingress`. Para tenants de tipo `static_site` hay un paso extra (`tenant.py:107-110`): se espera a que el PVC quede `Bound` (timeout 30 s) y se consulta al `local-path-provisioner` la ruta física del directorio donde montó el volumen. Esa ruta es la que el operador necesita para subir el contenido.

> [!example] Respuesta del bot tras la aprobación
> Mensaje real recibido (parafraseado por el LLM):
> ```
> El tenant está listo: https://saasphere.saasphere.local.
> El contenido está montado en /usr/share/nginx/html y se copió desde
> matrix:/var/lib/rancher/k3s/storage/pvc-3a6c6843-7099-4afa-a6ac-588eda77d311saaspheresaasphere-html.
> ¿Necesita verificar algo específico?
> ```
>
> Mensaje literal devuelto por la tool (`_deploy_message` en `tenant.py:295-297`, antes de pasar por el LLM):
> ```
> tenant deployed: https://saasphere.saasphere.local;
> scp target: matrix:/var/lib/rancher/k3s/storage/pvc-3a6c6843-7099-4afa-a6ac-588eda77d311_saasphere_saasphere-html
> ```
>
> Comparando ambos: la versión parafraseada **se ha comido los guiones bajos** entre el UUID, el namespace y el nombre del PVC. Ver Fricción F1 en la sección final.

---

### 5. Subida del contenido al PVC

> [!tip] Explicación para el TFG
> El `local-path-provisioner` de K3s monta un directorio del nodo directamente en `/usr/share/nginx/html` del pod, así que cualquier archivo que aparezca en esa ruta del nodo lo sirve nginx al instante, sin reinicio. El directorio del PVC pertenece a root, así que la subida desde el portátil se hace en dos pasos: `scp` a `/tmp/` del nodo (escribible) seguido de `sudo mv` al directorio definitivo. Se encadenan con `&&` para que sea una sola línea.

> [!example] Comando ejecutado desde el portátil
> ```bash
> scp ~/futuraweb/{index.html,SaaSphere.html,SaaSphere-logo.png} matrix:/tmp/ && \
> ssh matrix 'sudo mv /tmp/index.html /tmp/SaaSphere.html /tmp/SaaSphere-logo.png \
>   /var/lib/rancher/k3s/storage/pvc-3a6c6843-7099-4afa-a6ac-588eda77d311_saasphere_saasphere-html/ && \
>   sudo chmod o+r /var/lib/rancher/k3s/storage/pvc-3a6c6843-7099-4afa-a6ac-588eda77d311_saasphere_saasphere-html/*'
> ```
>
> Verificación desde dentro del pod (no requiere `sudo` en el nodo):
> ```bash
> ssh matrix 'k3s kubectl -n saasphere exec deploy/saasphere -- ls -la /usr/share/nginx/html'
> ```
> ```
> -rw-rw-r-- 1 1000 1000 2148308 May 16 17:10 SaaSphere-logo.png
> -rw-rw-r-- 1 1000 1000   86782 May 16 17:10 SaaSphere.html
> -rw-rw-r-- 1 1000 1000     101 May 16 17:10 index.html
> ```

---

### 6. Verificación HTTP y resolución del hostname

> [!tip] Explicación para el TFG
> El Ingress del tenant lo expone Traefik, que en K3s con `servicelb` recibe una IP propia distinta de la del nodo. En este cluster, el nodo `matrix` es `192.168.1.202`, pero el LoadBalancer de Traefik vive en `192.168.1.240`. El `/etc/hosts` del portátil debe apuntar al `.240`, no al nodo. Para evitar tocar `/etc/hosts` durante la validación, basta con pasar la cabecera `Host` a `curl`.

> [!example] Verificación con `curl`
> ```bash
> curl -sS -o /dev/null -w "%{http_code} %{size_download}\n" \
>   -H "Host: saasphere.saasphere.local" http://192.168.1.240/
> curl -sS -o /dev/null -w "%{http_code} %{size_download}\n" \
>   -H "Host: saasphere.saasphere.local" http://192.168.1.240/SaaSphere.html
> curl -sS -o /dev/null -w "%{http_code} %{size_download}\n" \
>   -H "Host: saasphere.saasphere.local" http://192.168.1.240/SaaSphere-logo.png
> ```
> ```
> 200 101
> 200 86782
> 200 2148308
> ```
>
> Para acceso desde el navegador del portátil:
> ```bash
> echo "192.168.1.240  saasphere.saasphere.local" | sudo tee -a /etc/hosts
> ```

> [!success] Resultado
> El navegador resuelve `http://saasphere.saasphere.local` → carga `index.html` → ejecuta el `<meta http-equiv="refresh">` → muestra `SaaSphere.html` con su logo. **Primer cliente real desplegado y operativo.**

---

## Diagrama de flujo end-to-end

```
   [Angel en Telegram]
           │
           │  "despliega un tenant static_site llamado saasphere…"
           ▼
   ┌───────────────────────────┐
   │ handle_free_text          │  telegram/handlers.py:317
   │   case_use=CaseUse.CHAT   │
   └───────────────────────────┘
           │
           ▼
   ┌───────────────────────────┐
   │ LobsterAgent.run()       │
   │   modelo: qwen3:8b        │
   └───────────────────────────┘
           │
           │  tool call: deploy_tenant(name=…, tier=…, …)
           ▼
   ┌───────────────────────────┐
   │ policy.validate()         │
   │   por cada manifest       │
   └───────────────────────────┘
           │
           ▼
   ┌───────────────────────────┐
   │ ApprovalManager           │  severity=CRITICAL
   │   format_approval_request │  timeout 3600 s
   │   + inline keyboard       │  recordatorios cada 60 s
   └───────────────────────────┘
           │
           │  Angel pulsa 👇 "Aprobar"
           ▼
   ┌───────────────────────────┐
   │ K8sClient.apply_manifest  │  Ns → PVC → Quota
   │   _dependency_order       │       → Deploy → Svc → Ingress
   └───────────────────────────┘
           │
           ▼
   ┌───────────────────────────┐
   │ wait_for_pvc_bound        │  solo static_site
   │ get_pvc_host_path         │  → ruta física en el nodo
   └───────────────────────────┘
           │
           ▼
   ┌───────────────────────────┐
   │ _deploy_message           │  "scp target: matrix:<host_path>"
   └───────────────────────────┘
           │
           │  el LLM parafrasea y se come los `_` (Fricción F1)
           ▼
        Telegram
           │
           ▼
   [Angel: scp + sudo mv ~/futuraweb/* al host_path]
           │
           ▼
   curl -H "Host: saasphere.saasphere.local" http://192.168.1.240/
                            → 200 OK
```

---

## Recursos creados en el cluster

| Recurso                            | Tipo                       | Detalle                                                                              |
| ---------------------------------- | -------------------------- | ------------------------------------------------------------------------------------ |
| `saasphere`                        | Namespace                  | Labels `saasphere.io/tenant=true`, `tier=free`, `type=static_site`, `owner=angel`    |
| `saasphere-html`                   | PersistentVolumeClaim      | 1 Gi, `local-path`, RWO                                                              |
| `saasphere-quota`                  | ResourceQuota              | 50m/200m CPU, 64Mi/256Mi memoria, 1 PVC, 1Gi storage                                 |
| `saasphere`                        | Deployment                 | `nginx:alpine`, 1 réplica, monta el PVC en `/usr/share/nginx/html`                   |
| `saasphere`                        | Service                    | ClusterIP, puerto 80                                                                 |
| `saasphere`                        | Ingress                    | Traefik, host `saasphere.saasphere.local`, IP `192.168.1.240`                        |
| Fila en `decisions`                | SQLite (Lobster)          | `case_use=chat`, `tools_called=["deploy_tenant"]`                                    |
| Fila en `actions`                  | SQLite (Lobster)          | `action_type=deploy_tenant`, `status=completed`, `payload` con namespace y hostname  |
| Fila en `approvals`                | SQLite (Lobster)          | `severity=critical`, `status=approved`, decisor = Angel                              |

Trazabilidad desde la CLI:

```bash
uv run lobster decisions list   # fila con la decisión del LLM
uv run lobster actions list     # fila deploy_tenant completed (host_path literal)
uv run lobster approvals list   # fila critical approved
```

---

## Fricciones encontradas y mitigaciones

Esta sección no es decorativa. Las tres fricciones que siguen aparecieron **durante la ejecución real** del despliegue documentado y representan el tipo de fallo que el TFG debe poder analizar: no errores de código, sino fricciones en el punto donde el LLM, la infraestructura y el operador humano se cruzan.

### F1 — El LLM se come los `_` del `host_path`

> [!warning] Manifestación
> La tool `deploy_tenant` devuelve un mensaje con la ruta física del PVC, que sigue el patrón `pvc-<uuid>_<namespace>_<pvc-name>` del `local-path-provisioner`. Ese mensaje pasa por `qwen3:8b` (CHAT) antes de llegar al chat: el modelo lo parafrasea y `handle_free_text` lo formatea con `md_to_mdv2` (`telegram/handlers.py:339`). En MarkdownV2 los guiones bajos delimitan *italic*, así que `_saasphere_saasphere-html` se renderiza sin los `_` envolventes y el operador recibe `saaspheresaasphere-html`. Un `scp` a esa ruta inventada falla con `No such file or directory`.

> [!tip] Mitigación inmediata
> Consultar el ledger en lugar de fiarse del mensaje del bot. La fila más reciente de `actions` trae el `host_path` literal sin paráfrasis:
> ```bash
> uv run lobster actions list
> ```
> Alternativa: listar los PVCs del nodo para reconstruir el path:
> ```bash
> ssh matrix 'sudo ls /var/lib/rancher/k3s/storage/ | grep saasphere'
> ```

> [!tip] Mejora propuesta
> En `_deploy_message` (`tenant.py:295`) envolver el `host_path` entre backticks (`` ` ``) para que MarkdownV2 lo trate como `code` y preserve los `_`. Otra opción: cuando el contenido sea técnico (paths, comandos), enviar el bloque con `parse_mode=None` o usar `escape_markdown_v2` antes de concatenar.

### F2 — IP del nodo ≠ IP del ingress

> [!warning] Manifestación
> El nodo K3s `matrix` es `192.168.1.202`, pero el Ingress de Traefik está expuesto por `servicelb` en `192.168.1.240`. Apuntar `/etc/hosts` al nodo es un error razonable (es donde corre el pod, al fin y al cabo) y se traduce en `curl: (7) Failed to connect to 192.168.1.202 port 80`.

> [!tip] Mitigación inmediata
> Leer la columna `ADDRESS` del Ingress, no asumir:
> ```bash
> ssh matrix 'k3s kubectl -n saasphere get ingress'
> ```

> [!tip] Mejora propuesta
> Que `deploy_tenant` resuelva la IP real del Ingress tras `wait_for_pvc_bound` y la añada al `payload` y al mensaje final. La línea sugerida en el bot:
> ```
> tenant deployed: http://saasphere.saasphere.local (192.168.1.240); scp target: …
> ```

### F3 — `sudo mv` "aparentemente fallido"

> [!warning] Manifestación
> Al subir el contenido al PVC, la primera ejecución del `sudo mv` (combinado tras `scp`) completó correctamente. El operador, sin tener confirmación visual del éxito (el comando no produce salida cuando funciona) y queriendo reintentar con `su` por comodidad, lanzó el `mv` de nuevo en una sesión nueva. Esta vez los archivos ya no estaban en `/tmp` (acababan de moverse) y la salida `mv: no se puede efectuar 'stat' sobre '/tmp/index.html': No existe el fichero` le hizo asumir que **nunca habían llegado** al PVC.

> [!tip] Mitigación inmediata
> Antes de reintentar un `mv` destructivo del estado intermedio, comprobar el destino. Mejor aún, comprobarlo desde dentro del pod (más fiable que el filesystem del nodo, porque elimina ambigüedad de path y permisos):
> ```bash
> ssh matrix 'k3s kubectl -n saasphere exec deploy/saasphere -- ls -la /usr/share/nginx/html'
> ```
>
> El `journalctl` del nodo es la fuente de verdad de qué `sudo` se ejecutó cuándo:
> ```bash
> ssh matrix 'journalctl --since "1h ago" | grep "USER=root ; COMMAND=/usr/bin/mv"'
> ```

> [!tip] Mejora propuesta
> Construir un script wrapper `lobster-upload <tenant> <archivos…>` que (1) consulte el `host_path` real desde la DB de Lobster, (2) haga el `scp + sudo mv` con verificación post-mv, y (3) liste el resultado desde dentro del pod. El operador quedaría aislado de `local-path` y de las dos sesiones SSH.

---

## Decisiones de diseño

| Decisión                                                | Alternativa descartada                                | Razón                                                                                                                            |
| ------------------------------------------------------- | ----------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| `name="saasphere"`                                      | `name="saasphere-es"`                                 | Brevedad y porque aún no hay múltiples tenants del proyecto SaaSphere. Si surgen, se renombrará el primero a `saasphere-main`.    |
| Hostname `saasphere.saasphere.local`                    | Dominio público `saasphere.es` con Let's Encrypt      | Exige cert-manager + DNS público + port-forward. Se deja para una fase posterior dedicada a HTTPS público.                       |
| Subida via `scp` + `sudo mv` al `host_path`             | Construir imagen Docker custom con los archivos       | No requiere registry, es más didáctica y refleja exactamente el flujo previsto por `_deploy_message`. Para producción se cambia. |
| Severity `CRITICAL` hardcoded en `deploy_tenant`        | Severity configurable por usuario o por policy        | Crear un tenant es irreversible-light (namespace, quotas, ingress potencialmente expuesto). No tiene sentido permitir `AUTONOMOUS`.|
| Aprobación humana via inline keyboard de Telegram       | Endpoint HTTP firmado o aprobación por email          | Telegram ya es el canal del operador, soporta inline keyboards nativos y `aiogram` lo maneja con `callback_query`.               |
| `local-path` storage class para el PVC                  | `longhorn` o NFS                                      | `local-path` viene con K3s, es trivial y el sitio cabe en 1 Gi en el nodo. Para multi-replica habría que cambiar.                |
| Tier `free` (50m/200m CPU, 64Mi/256Mi mem)              | Tier `basic` o `premium`                              | El sitio es estático y diminuto (2,2 MB). El `free` está sobrado y permite probar las cuotas más restrictivas.                   |

---

## Trazabilidad y verificación end-to-end

> [!example] Inspección del ledger
> ```bash
> uv run lobster decisions list
> uv run lobster actions list
> uv run lobster approvals list
> ```

> [!example] Health del tenant vía bot (read-only, sin aprobación)
> Texto al bot:
> ```
> Verifica el tenant saasphere
> ```
> El LLM llama a `verify_tenant_health(namespace="saasphere")` y devuelve estado del pod, ingress y eventos recientes.

> [!example] Comprobación HTTP repetible
> ```bash
> for path in "/" "/SaaSphere.html" "/SaaSphere-logo.png"; do
>   curl -sS -o /dev/null -w "$path → HTTP %{http_code} %{size_download} bytes\n" \
>     -H "Host: saasphere.saasphere.local" "http://192.168.1.240$path"
> done
> ```

---

## Lo que queda por hacer

> [!todo] Próximos pasos sobre este tenant
> - [ ] Sustituir `nginx:alpine` por una imagen Docker propia con el contenido incrustado (elimina el `scp + sudo mv` y hace el tenant inmutable).
> - [ ] Migrar `saasphere.saasphere.local` a `saasphere.es` real con cert-manager + Let's Encrypt cuando se exponga el cluster al exterior.
> - [ ] Implementar las mejoras F1/F2/F3 descritas en "Fricciones encontradas y mitigaciones".
> - [ ] Añadir un script `lobster-upload` que esconda el detalle del `host_path` al operador.
> - [ ] Documentar el flujo de `delete_tenant` con el mismo nivel de detalle (también CRITICAL).

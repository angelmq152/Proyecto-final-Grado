# Fase 7.0 — Funcionamiento de LeIA

> [!abstract] Resumen
> Punto de apertura del capítulo **7. Fase 7 – Despliegue de LeIA** del TFG, redactado para insertarse antes de la subfase 7.a («Esqueleto»). Explica, en estilo impersonal y con detalle técnico, qué es LeIA, cómo está estructurada internamente, cómo selecciona el modelo según la tarea, qué política de seguridad la gobierna, qué recorrido sigue una mutación desde que se dispara hasta que se registra y cómo se garantiza su trazabilidad. Aproximadamente dos páginas en Calibri 11 pt.

---

LeIA es el agente autónomo de inteligencia artificial que opera la plataforma SaaSphere. Se materializa como un servicio Python (paquete `lobster_agent`, ejecutable `lobster`) que se ejecuta en el nodo físico LeIA, dedicado precisamente a este propósito por disponer de la GPU NVIDIA RTX 3060 Ti requerida para la inferencia local. Su misión es doble: vigilar el clúster K3s de forma continua y ejecutar acciones correctivas sobre los *tenants* sin necesidad de intervención humana, salvo en aquellas operaciones que la política de seguridad clasifica como sensibles. El uso de inferencia local mediante Ollama y los modelos Qwen3 elimina la dependencia de APIs externas, suprime el coste por *token* y mantiene los datos de los clientes dentro de la infraestructura.

## Componentes internos

El agente se estructura en torno a cinco bloques coordinados:

- **Núcleo de razonamiento (`LobsterAgent`)**. Receptor único de las peticiones del sistema. Cada petición se etiqueta con un *caso de uso* (modo de operación) que determina qué modelo emplear y qué subconjunto de herramientas habilitar. El núcleo se apoya en Pydantic AI para encapsular el ciclo *prompt → invocación de herramienta → respuesta* y en Ollama como servidor de inferencia local.
- **Capa de herramientas**. Conjunto de funciones tipadas que el modelo puede invocar. Se dividen en herramientas de lectura (consulta de Prometheus, Loki, Kubernetes, Alertmanager y la propia base de datos del agente) y herramientas de mutación (reinicio de pods, escalado de despliegues, alta y baja de tenants a partir de plantillas Jinja2).
- **Política y validación (`policy.validate`)**. Función que se invoca antes de cada mutación. Determina si la acción está permitida y, en caso afirmativo, le asigna una severidad. Ninguna mutación llega al clúster sin pasar por esta validación.
- **Gestor de aprobaciones (`ApprovalManager`)**. Cuando la severidad supera el umbral autónomo, el agente envía una solicitud de aprobación al operador mediante Telegram y bloquea la ejecución hasta recibir respuesta. La respuesta se registra y se asocia a la acción que la motivó.
- **Persistencia y observabilidad**. Una base de datos SQLite con nueve tablas almacena el historial completo del agente; un *endpoint* `/metrics` en FastAPI expone métricas Prometheus para su consumo desde Grafana.

## Casos de uso y selección del modelo

LeIA opera en catorce modos distintos. Cada modo asocia un objetivo concreto a un modelo y a un conjunto de herramientas. La selección entre los dos modelos disponibles —`qwen3:8b`, rápido, y `qwen3:32b`, más lento pero con mayor capacidad de razonamiento— se realiza en función del compromiso entre velocidad y profundidad que cada tarea requiere.

| Familia               | Casos de uso                                                                                   | Modelo                                                 | Razonamiento extendido (*think*)                                                                                                       |
| --------------------- | ---------------------------------------------------------------------------------------------- | ------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------- |
| Lazos periódicos      | `health_loop_read`, `health_loop_analyze`, `global_state`, `optimization`, `summary`, `backup` | `qwen3:8b`                                             | Activo en estado global y optimización; desactivado en los lazos de salud para garantizar la fiabilidad de las llamadas a herramientas |
| Operación con cliente | `onboarding`, `diagnose`, `daily_summary`                                                      | `qwen3:32b`                                            | Activo en *onboarding* y *diagnose*; desactivado en el resumen diario                                                                  |
| Reactivos             | `alert_reactive`                                                                               | `qwen3:8b`                                             | Desactivado, por la misma razón que en los lazos de salud                                                                              |
| Conversación          | `chat`, `conversation`, `think`                                                                | `qwen3:8b` para `chat`, `qwen3:32b` para los otros dos | Activo en `conversation` y `think`                                                                                                     |

El razonamiento extendido (modo `/think` de Qwen3) ofrece respuestas más elaboradas, pero se ha observado que en ciertos modos provoca que el modelo emita las llamadas a herramientas como texto en lugar de invocarlas. Por ese motivo se desactiva en los modos que deben ejecutar mutaciones con la máxima fiabilidad.

## Política de seguridad y severidad

Toda mutación pasa por la función de validación, que combina varias capas de control:

1. **Espacios de nombres bloqueados de raíz** (`kube-system`, `kube-public`, `metallb-system`, `saasphere-system`). Ninguna acción puede modificarlos.
2. **Lista blanca de tenants**. Solo se admiten mutaciones sobre espacios de nombres con la etiqueta `saasphere.io/tenant=true`. Cualquier otro destino se rechaza.
3. **Tipos de manifiesto prohibidos** (`Secret`, `ServiceAccount`, `Role`, `RoleBinding`, `ClusterRole`, `ClusterRoleBinding`, `Pod`). Se impide así la escalada de privilegios y la creación de cargas sin controlador.
4. **Antipatrones de seguridad**. Se rechazan los manifiestos con `privileged=true`, montajes `hostPath`, `hostNetwork`, `hostPID`, `hostIPC` o sin límites de CPU y memoria declarados.
5. **Recursos protegidos de la plataforma**. Los nombres `traefik`, `coredns` y `metrics-server` no pueden ser destino de ninguna acción.

Si la validación se supera, la acción recibe una severidad de entre tres niveles:

| Severidad    | Comportamiento                                                               | Acciones representativas                                                                                            |
| ------------ | ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| `AUTONOMOUS` | El agente actúa sin pedir confirmación                                       | Todas las lecturas, reanudación de tenants pausados, verificación de salud, anotaciones, despinchado de despliegues |
| `NORMAL`     | Requiere aprobación humana por Telegram con un tiempo de espera estándar     | Reinicios de pod y de despliegue, escalados, aplicación de manifiestos, pausa de tenant, fijación a nodo            |
| `CRITICAL`   | Requiere aprobación con tiempo de espera ampliado y recordatorios periódicos | Alta y baja de tenants, escalado a cero réplicas si no había una operación previa de *scale-to-zero*                |

## Ciclo de una mutación

El recorrido que sigue cualquier mutación, desde su disparo hasta su registro, se compone de las siguientes etapas:

1. **Disparo**. Un *scheduler* periódico, un evento de Kubernetes, una alerta de Alertmanager o un mensaje del operador desencadenan la ejecución de un caso de uso concreto.
2. **Razonamiento**. El núcleo construye el *prompt* específico del caso de uso, invoca al modelo correspondiente y recibe la propuesta de herramienta a ejecutar.
3. **Validación**. La envoltura común de mutaciones (`MutationContext`) invoca a la política, que devuelve la decisión de permiso y la severidad asignada.
4. **Aprobación (cuando procede)**. Si la severidad es `NORMAL` o `CRITICAL`, el gestor de aprobaciones envía la solicitud por Telegram con botones en línea y suspende la ejecución hasta recibir respuesta.
5. **Modo de ejecución**. Si el agente se encuentra en modo `dry_run`, la acción se simula sin tocar el clúster. Si está en modo `paused`, la ejecución se descarta. En modo `normal`, la acción se aplica realmente.
6. **Registro**. La acción se asienta en la tabla `actions` con su severidad, su decisión asociada y su resultado. La aprobación, si la hubo, queda en la tabla `approvals`. Cualquier evento intermedio relevante se inscribe en la tabla `events`.

## Trazabilidad

La base de datos SQLite del agente concentra toda la información necesaria para auditar su comportamiento. Sus nueve tablas son las siguientes:

- `decisions` — cada inferencia del modelo, con caso de uso, modelo empleado, latencia y consumo de *tokens*.
- `actions` — cada mutación intentada, ejecutada o rechazada.
- `approvals` — cada solicitud de aprobación y su resolución.
- `agent_state` — estado actual del agente (`normal`, `dry_run`, `paused`).
- `conversation_turns` — historial de los diálogos por chat de Telegram.
- `tool_requests` — peticiones internas de nuevas herramientas detectadas por el propio agente.
- `events` — flujo unificado de eventos para análisis posterior.
- `tenant_state` — estado conocido de cada *tenant* (activo, pausado, reubicado en *Fallback*).
- `metrics_snapshots` — capturas periódicas de métricas usadas para análisis a posteriori.

Esta persistencia, combinada con las métricas expuestas en `/metrics` y los registros agregados en Loki, permite reconstruir por qué LeIA tomó cualquier decisión en cualquier instante, requisito imprescindible para confiar en un agente que opera sobre infraestructura en producción.

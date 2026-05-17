---
title: Systemd y despliegue
tags: [infraestructura, systemd, deploy, leia]
---

# 🚀 Systemd y despliegue en LeIA

> [!abstract] Servicio gestionado por systemd
> Lobster corre como **unit de systemd** en LeIA, ejecutado por el usuario `lobster`. Restart automático en fallos, dependencia explícita de Ollama, journald como logger primario.

## 📄 Unit típico

> [!example] `/etc/systemd/system/lobster.service`
> ```ini
> [Unit]
> Description=Lobster — SaaSphere AI Orchestrator
> After=network-online.target ollama.service
> Wants=network-online.target
> Requires=ollama.service
>
> [Service]
> Type=simple
> User=lobster
> Group=lobster
> WorkingDirectory=/opt/lobster
> EnvironmentFile=/etc/lobster/.env
> ExecStart=/usr/local/bin/uv run lobster
> Restart=on-failure
> RestartSec=5s
> StandardOutput=journal
> StandardError=journal
>
> [Install]
> WantedBy=multi-user.target
> ```

> [!info] `uv run lobster` desde el WorkingDirectory
> El binario `lobster` está definido en `pyproject.toml`:
> ```toml
> [project.scripts]
> lobster = "lobster.__main__:main"
> ```

## 🚀 Lifecycle commands

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now lobster

# Estado
sudo systemctl status lobster

# Logs en vivo
sudo journalctl -u lobster -f

# Reinicio limpio
sudo systemctl restart lobster
```

## 🔁 Restart en fallos

> [!tip] `Restart=on-failure` + `RestartSec=5s`
> Si Lobster se cae (excepción no capturada en lifespan), systemd lo reinicia tras 5 s. Eso dispara la alerta `LobsterRestart` (severity=info) en Prometheus.

> [!warning] No usa `Restart=always`
> `always` reiniciaría incluso si Lobster se apaga limpiamente. `on-failure` permite parar manualmente sin recidiva.

## 📂 Estructura en LeIA

```text
/opt/lobster/                    # working dir (clone del repo)
/etc/lobster/
├── .env                          # secrets (token Telegram, etc.)
├── config.toml                   # configuración general
└── kubeconfig                    # acceso a K3s
/var/lib/lobster/
└── state.db                      # SQLite
/opt/lobster/obsidian/           # vault donde se guardan los daily_summary
/usr/local/bin/uv                 # gestor de paquetes
```

## ⚙️ Variables de entorno típicas

> [!example] `/etc/lobster/.env`
> ```bash
> LOBSTER_TELEGRAM__BOT_TOKEN=123:abc
> LOBSTER_TELEGRAM__ALLOWED_USER_IDS=[123456789]
> LOBSTER_TELEGRAM__ENABLED=true
> LOBSTER_ENVIRONMENT=prod
> LOBSTER_LOG_LEVEL=INFO
> ```
> Los valores ya cubiertos por defecto (URLs de Prometheus, etc.) se pueden omitir.

## 📜 Configuración TOML

> [!example] `/etc/lobster/config.toml`
> ```toml
> environment = "prod"
> log_level = "INFO"
>
> [prometheus]
> url = "http://192.168.1.201:9090"
>
> [loki]
> url = "http://192.168.1.201:3100"
>
> [k8s]
> kubeconfig_path = "/etc/lobster/kubeconfig"
>
> [http]
> host = "0.0.0.0"
> port = 8080
>
> [agent]
> enable_dummy_tools = false
> max_conversation_turns = 20
> dry_run_default = false
> enforce_resource_limits = true
>
> [scheduler]
> timezone = "Europe/Madrid"
> daily_summary_hour = 8
> ```

## 🆙 Actualizar Lobster

```bash
cd /opt/lobster
sudo systemctl stop lobster
git pull
uv sync
uv run lobster db migrate
sudo systemctl start lobster
```

> [!warning] El stop limpio es mejor
> `lifespan` cancela tasks (scheduler, watcher, telegram, approval loop) y cierra conexiones (httpx, sqlite). Si haces `kill -9` puedes dejar locks de SQLite o sesiones HTTPS abiertas.

## 🔐 Usuario `lobster`

> [!info] Usuario sin privilegios
> Crear el usuario:
> ```bash
> sudo useradd -r -s /usr/sbin/nologin lobster
> sudo chown -R lobster:lobster /opt/lobster /var/lib/lobster
> ```
> Es deliberado que **no pueda hacer login interactivo**.

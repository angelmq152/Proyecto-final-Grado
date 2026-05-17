from typing import Literal

from pydantic import BaseModel
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)


class LokiConfig(BaseModel):
    url: str = "http://192.168.1.201:3100"
    push_path: str = "/loki/api/v1/push"
    batch_size: int = 100
    flush_interval_seconds: int = 5
    timeout_seconds: float = 5.0


class PrometheusConfig(BaseModel):
    url: str = "http://192.168.1.201:9090"
    timeout_seconds: float = 5.0


class AlertmanagerConfig(BaseModel):
    url: str = "http://192.168.1.201:9093"
    timeout_seconds: float = 5.0


class K8sConfig(BaseModel):
    kubeconfig_path: str = "/etc/lobster/kubeconfig"
    in_cluster: bool = False
    timeout_seconds: float = 10.0


class DatabaseConfig(BaseModel):
    url: str = "sqlite+aiosqlite:////var/lib/lobster/state.db"


class OllamaConfig(BaseModel):
    base_url: str = "http://localhost:11434/v1"
    api_key: str = "ollama"
    timeout_seconds: float = 180.0


class HTTPConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8080


class AgentConfig(BaseModel):
    enable_dummy_tools: bool = False
    max_conversation_turns: int = 20
    dry_run_default: bool = False
    enforce_resource_limits: bool = True


class TelegramConfig(BaseModel):
    bot_token: str = ""
    allowed_user_ids: list[int] = []
    enabled: bool = False
    polling_timeout_seconds: int = 30


class ApprovalConfig(BaseModel):
    default_timeout_seconds: int = 600
    critical_timeout_seconds: int = 3600
    critical_reminder_interval_seconds: int = 60
    max_pending_approvals: int = 50


class SchedulerConfig(BaseModel):
    timezone: str = "Europe/Madrid"
    health_loop_interval_minutes: int = 5
    global_state_interval_minutes: int = 30
    hourly_summary_enabled: bool = True
    daily_summary_hour: int = 8
    daily_summary_minute: int = 0
    backup_hour: int = 2
    backup_minute: int = 0
    optimization_hour: int = 3
    optimization_minute: int = 0
    k8s_watcher_enabled: bool = True
    k8s_watcher_reconnect_delay_seconds: float = 5.0
    k8s_watcher_max_reconnect_delay_seconds: float = 120.0
    obsidian_path: str = "/opt/lobster/obsidian"
    node_pressure_cpu_threshold_pct: float = 85.0
    node_pressure_memory_threshold_pct: float = 85.0
    node_pressure_unpin_cpu_threshold_pct: float = 70.0
    node_pressure_unpin_memory_threshold_pct: float = 70.0
    node_pressure_unpin_stable_minutes: int = 15


class Settings(BaseSettings):
    environment: Literal["dev", "prod"] = "prod"
    log_level: str = "INFO"
    loki: LokiConfig = LokiConfig()
    prometheus: PrometheusConfig = PrometheusConfig()
    alertmanager: AlertmanagerConfig = AlertmanagerConfig()
    k8s: K8sConfig = K8sConfig()
    http: HTTPConfig = HTTPConfig()
    agent: AgentConfig = AgentConfig()
    telegram: TelegramConfig = TelegramConfig()
    approval: ApprovalConfig = ApprovalConfig()
    database: DatabaseConfig = DatabaseConfig()
    ollama: OllamaConfig = OllamaConfig()
    scheduler: SchedulerConfig = SchedulerConfig()

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            TomlConfigSettingsSource(settings_cls),
            file_secret_settings,
        )

    model_config = SettingsConfigDict(
        env_prefix="LOBSTER_",
        env_nested_delimiter="__",
        env_file="/etc/lobster/.env",
        toml_file="/etc/lobster/config.toml",
        extra="ignore",
    )

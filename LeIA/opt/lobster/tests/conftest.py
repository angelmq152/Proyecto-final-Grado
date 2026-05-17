import pytest
from fastapi.testclient import TestClient
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from lobster_agent.config import Settings


def make_test_settings(**kwargs: object) -> Settings:
    """Crea Settings para tests sin leer ficheros del sistema."""

    class _TestSettings(Settings):
        model_config = SettingsConfigDict(
            env_prefix="LOBSTER_",
            env_nested_delimiter="__",
            env_file=None,
            toml_file=None,
            extra="ignore",
        )

        @classmethod
        def settings_customise_sources(
            cls,
            settings_cls: type[BaseSettings],
            init_settings: PydanticBaseSettingsSource,
            env_settings: PydanticBaseSettingsSource,
            dotenv_settings: PydanticBaseSettingsSource,
            file_secret_settings: PydanticBaseSettingsSource,
        ) -> tuple[PydanticBaseSettingsSource, ...]:
            return (init_settings, env_settings)

    return _TestSettings(**kwargs)  # type: ignore[return-value]


@pytest.fixture
def settings() -> Settings:
    return make_test_settings(environment="dev", log_level="INFO")


@pytest.fixture
def client(settings: Settings) -> TestClient:
    from lobster_agent.main import create_app

    app = create_app(settings)
    return TestClient(app, raise_server_exceptions=True)

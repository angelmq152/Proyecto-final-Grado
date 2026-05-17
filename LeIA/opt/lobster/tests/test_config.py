import pytest

from tests.conftest import make_test_settings


def test_default_values() -> None:
    s = make_test_settings()
    assert s.environment in ("dev", "prod")
    assert s.http.port == 8080
    assert "3100" in s.loki.url
    assert s.loki.timeout_seconds == 5.0
    assert s.prometheus.url == "http://192.168.1.201:9090"
    assert s.prometheus.timeout_seconds == 5.0
    assert s.alertmanager.url == "http://192.168.1.201:9093"
    assert s.alertmanager.timeout_seconds == 5.0
    assert s.k8s.kubeconfig_path == "/etc/lobster/kubeconfig"
    assert s.k8s.in_cluster is False
    assert s.k8s.timeout_seconds == 10.0
    assert s.telegram.enabled is False
    assert s.telegram.allowed_user_ids == []
    assert s.approval.default_timeout_seconds == 600
    assert s.agent.dry_run_default is False
    assert s.agent.enforce_resource_limits is True


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOBSTER_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("LOBSTER_ALERTMANAGER__URL", "http://alertmanager.test")
    monkeypatch.setenv("LOBSTER_ALERTMANAGER__TIMEOUT_SECONDS", "9.5")
    monkeypatch.setenv("LOBSTER_K8S__KUBECONFIG_PATH", "/tmp/lobster-kubeconfig")
    monkeypatch.setenv("LOBSTER_K8S__IN_CLUSTER", "true")
    monkeypatch.setenv("LOBSTER_TELEGRAM__ENABLED", "true")
    monkeypatch.setenv("LOBSTER_TELEGRAM__ALLOWED_USER_IDS", "[111,222]")
    s = make_test_settings()
    assert s.log_level == "DEBUG"
    assert s.alertmanager.url == "http://alertmanager.test"
    assert s.alertmanager.timeout_seconds == 9.5
    assert s.k8s.kubeconfig_path == "/tmp/lobster-kubeconfig"
    assert s.k8s.in_cluster is True
    assert s.telegram.enabled is True
    assert s.telegram.allowed_user_ids == [111, 222]


def test_database_default_url() -> None:
    settings = make_test_settings()
    assert settings.database.url == "sqlite+aiosqlite:////var/lib/lobster/state.db"

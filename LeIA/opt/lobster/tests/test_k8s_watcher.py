from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from lobster_agent.config import SchedulerConfig
from lobster_agent.k8s_watcher import (
    K8sWatcher,
    _event_message,
    _event_name,
    _event_namespace,
    _event_reason,
    _is_critical_event,
)

# ── helpers ──────────────────────────────────────────────────────────────────


def _make_event(
    event_type: str = "Warning",
    reason: str = "BackOff",
    message: str = "Back-off restarting failed container",
    namespace: str = "tenant-foo",
    name: str = "my-pod-abc",
) -> MagicMock:
    event = MagicMock()
    event.type = event_type
    event.reason = reason
    event.message = message

    metadata = MagicMock()
    metadata.namespace = namespace
    metadata.name = f"my-pod-abc.{uuid4().hex[:8]}"
    event.metadata = metadata

    involved = MagicMock()
    involved.name = name
    event.involvedObject = involved

    return event


def _make_watcher(k8s_watcher_enabled: bool = True) -> tuple[K8sWatcher, MagicMock, MagicMock]:
    config = SchedulerConfig(
        timezone="UTC",
        k8s_watcher_enabled=k8s_watcher_enabled,
        k8s_watcher_reconnect_delay_seconds=0.01,
        k8s_watcher_max_reconnect_delay_seconds=0.05,
    )
    agent = MagicMock()
    agent.run = AsyncMock(
        return_value=MagicMock(outcome="success", data="Analizado OK.", decision_id=uuid4())
    )
    notifier = MagicMock()
    notifier.send_to_admin = AsyncMock()
    watcher = K8sWatcher("/fake/kubeconfig", config, agent, notifier)
    return watcher, agent, notifier


# ── _is_critical_event ────────────────────────────────────────────────────────


def test_critical_event_backoff():
    event = _make_event(event_type="Warning", reason="BackOff")
    assert _is_critical_event(event) is True


def test_critical_event_oomkilling():
    event = _make_event(event_type="Warning", reason="OOMKilling")
    assert _is_critical_event(event) is True


def test_critical_event_crashloop():
    event = _make_event(event_type="Warning", reason="CrashLoopBackOff")
    assert _is_critical_event(event) is True


def test_critical_event_killing():
    event = _make_event(event_type="Warning", reason="Killing")
    assert _is_critical_event(event) is True


def test_non_critical_normal_type():
    event = _make_event(event_type="Normal", reason="BackOff")
    assert _is_critical_event(event) is False


def test_non_critical_pulled_reason():
    event = _make_event(event_type="Normal", reason="Pulled")
    assert _is_critical_event(event) is False


def test_critical_event_failed():
    event = _make_event(event_type="Warning", reason="Failed")
    assert _is_critical_event(event) is True


# ── event field extractors ────────────────────────────────────────────────────


def test_event_namespace_extracted():
    event = _make_event(namespace="tenant-bar")
    assert _event_namespace(event) == "tenant-bar"


def test_event_name_from_involved_object():
    event = _make_event(name="my-pod-xyz")
    assert _event_name(event) == "my-pod-xyz"


def test_event_reason_extracted():
    event = _make_event(reason="BackOff")
    assert _event_reason(event) == "BackOff"


def test_event_message_truncated():
    long_msg = "x" * 600
    event = _make_event(message=long_msg)
    assert len(_event_message(event)) <= 500


# ── watcher lifecycle ─────────────────────────────────────────────────────────


async def test_watcher_disabled_does_not_start():
    watcher, agent, notifier = _make_watcher(k8s_watcher_enabled=False)
    await watcher.start()
    assert watcher._task is None
    await watcher.stop()


async def test_watcher_stop_when_not_started():
    watcher, _, _ = _make_watcher()
    await watcher.stop()  # Should not raise


# ── _handle_event ─────────────────────────────────────────────────────────────


async def test_handle_event_calls_agent():
    watcher, agent, notifier = _make_watcher()
    event = _make_event(reason="BackOff", namespace="tenant-foo", name="app-pod-123")

    await watcher._handle_event(event)

    agent.run.assert_called_once()
    from lobster_agent.agent.routing import CaseUse

    assert agent.run.call_args[0][0] == CaseUse.HEALTH_LOOP_ANALYZE
    prompt = agent.run.call_args[0][1]
    assert "BackOff" in prompt
    assert "tenant-foo" in prompt
    assert "app-pod-123" in prompt


async def test_handle_event_notifies_admin():
    watcher, agent, notifier = _make_watcher()
    event = _make_event(reason="OOMKilling", namespace="tenant-bar", name="app-pod-456")

    await watcher._handle_event(event)

    notifier.send_to_admin.assert_called_once()
    msg = notifier.send_to_admin.call_args[0][0]
    assert "OOMKilling" in msg
    assert "tenant" in msg  # hyphen is escaped as \- in MarkdownV2


async def test_handle_event_does_not_raise_on_agent_failure():
    watcher, agent, notifier = _make_watcher()
    agent.run = AsyncMock(side_effect=RuntimeError("agent down"))
    event = _make_event()

    await watcher._handle_event(event)

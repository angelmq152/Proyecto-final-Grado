from lobster_agent.agent.routing import CaseUse, select_model, use_think_mode


def test_select_model_uses_8b_for_fast_routine_cases() -> None:
    assert select_model(CaseUse.HEALTH_LOOP_READ) == "qwen3:8b"
    assert select_model(CaseUse.SUMMARY) == "qwen3:8b"
    assert select_model(CaseUse.BACKUP) == "qwen3:8b"


def test_select_model_uses_8b_for_reactive_cases() -> None:
    assert select_model(CaseUse.HEALTH_LOOP_ANALYZE) == "qwen3:8b"
    assert select_model(CaseUse.GLOBAL_STATE) == "qwen3:8b"
    assert select_model(CaseUse.OPTIMIZATION) == "qwen3:8b"
    assert select_model(CaseUse.ALERT_REACTIVE) == "qwen3:8b"


def test_select_model_uses_32b_for_deep_analysis() -> None:
    assert select_model(CaseUse.ONBOARDING) == "qwen3:32b"
    assert select_model(CaseUse.DIAGNOSE) == "qwen3:32b"
    assert select_model(CaseUse.CONVERSATION) == "qwen3:32b"
    assert select_model(CaseUse.DAILY_SUMMARY) == "qwen3:32b"


def test_use_think_mode_disabled_for_routine_cases() -> None:
    assert use_think_mode(CaseUse.HEALTH_LOOP_READ) is False
    assert use_think_mode(CaseUse.SUMMARY) is False
    assert use_think_mode(CaseUse.BACKUP) is False


def test_use_think_mode_disabled_for_action_cases() -> None:
    # HEALTH_LOOP_ANALYZE y ALERT_REACTIVE ejecutan mutations. Con /think
    # Qwen3 tiende a describir los tool calls en texto en lugar de invocarlos,
    # así que los mantenemos sin think para garantizar tool use real.
    assert use_think_mode(CaseUse.HEALTH_LOOP_ANALYZE) is False
    assert use_think_mode(CaseUse.ALERT_REACTIVE) is False
    assert use_think_mode(CaseUse.DAILY_SUMMARY) is False


def test_use_think_mode_enabled_for_reasoning_cases() -> None:
    assert use_think_mode(CaseUse.DIAGNOSE) is True
    assert use_think_mode(CaseUse.CONVERSATION) is True
    assert use_think_mode(CaseUse.THINK) is True

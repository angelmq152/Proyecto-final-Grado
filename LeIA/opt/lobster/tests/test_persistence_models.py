from lobster_agent.persistence.models import Decision


def test_decision_defaults() -> None:
    decision = Decision(
        case_use="conversation",
        model_used="qwen3:32b",
        think_mode=True,
        prompt_summary="hola",
        conclusion="ok",
    )

    assert decision.id is not None
    assert decision.trigger == "manual"
    assert decision.tokens_input == 0
    assert decision.tokens_output == 0
    assert decision.latency_ms == 0
    assert decision.tools_called == []
    assert decision.derived_actions == []

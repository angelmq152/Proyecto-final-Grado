from enum import StrEnum


class CaseUse(StrEnum):
    SMOKE_TEST = "smoke_test"
    HEALTH_LOOP_READ = "health_loop_read"
    HEALTH_LOOP_ANALYZE = "health_loop_analyze"
    GLOBAL_STATE = "global_state"
    OPTIMIZATION = "optimization"
    ONBOARDING = "onboarding"
    DIAGNOSE = "diagnose"
    SUMMARY = "summary"
    DAILY_SUMMARY = "daily_summary"
    BACKUP = "backup"
    ALERT_REACTIVE = "alert_reactive"
    CONVERSATION = "conversation"
    CHAT = "chat"
    THINK = "think"


def select_model(case_use: CaseUse) -> str:
    return {
        CaseUse.SMOKE_TEST: "qwen3:8b",
        CaseUse.HEALTH_LOOP_READ: "qwen3:8b",
        CaseUse.HEALTH_LOOP_ANALYZE: "qwen3:8b",
        CaseUse.GLOBAL_STATE: "qwen3:8b",
        CaseUse.OPTIMIZATION: "qwen3:8b",
        CaseUse.ONBOARDING: "qwen3:32b",
        CaseUse.DIAGNOSE: "qwen3:32b",
        CaseUse.SUMMARY: "qwen3:8b",
        CaseUse.DAILY_SUMMARY: "qwen3:32b",
        CaseUse.BACKUP: "qwen3:8b",
        CaseUse.ALERT_REACTIVE: "qwen3:8b",
        CaseUse.CONVERSATION: "qwen3:32b",
        CaseUse.CHAT: "qwen3:8b",
        CaseUse.THINK: "qwen3:32b",
    }[case_use]


def use_think_mode(case_use: CaseUse) -> bool:
    # Think mode (Qwen3 /think) suele causar que el modelo emita los tool calls
    # como texto (p.ej. <tools>...</tools>) en lugar de invocarlos. Por eso lo
    # desactivamos en daily_summary (5ff8e13) y aquí también en los modos que
    # deben ejecutar mutaciones de forma fiable: HEALTH_LOOP_ANALYZE (autónomo
    # en CrashLoopBackOff) y ALERT_REACTIVE (reacciona a alertas reales).
    return case_use not in {
        CaseUse.SMOKE_TEST,
        CaseUse.HEALTH_LOOP_READ,
        CaseUse.HEALTH_LOOP_ANALYZE,
        CaseUse.SUMMARY,
        CaseUse.DAILY_SUMMARY,
        CaseUse.BACKUP,
        CaseUse.ALERT_REACTIVE,
        CaseUse.CHAT,
    }

from enum import StrEnum


class ActionSeverity(StrEnum):
    AUTONOMOUS = "autonomous"
    NORMAL = "normal"
    CRITICAL = "critical"
    FORBIDDEN = "forbidden"

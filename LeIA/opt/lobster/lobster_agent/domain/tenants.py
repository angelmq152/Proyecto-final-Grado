from dataclasses import dataclass
from enum import StrEnum


class TenantTier(StrEnum):
    FREE = "free"
    BASIC = "basic"
    PREMIUM = "premium"


class TenantType(StrEnum):
    WORDPRESS = "wordpress"
    STATIC_SITE = "static_site"
    WEB_APP = "web_app"


@dataclass(frozen=True)
class TierLimits:
    cpu_request: str
    cpu_limit: str
    memory_request: str
    memory_limit: str
    replicas: int
    storage: str


TIER_LIMITS: dict[TenantTier, TierLimits] = {
    TenantTier.FREE: TierLimits("50m", "200m", "64Mi", "256Mi", 1, "1Gi"),
    TenantTier.BASIC: TierLimits("100m", "500m", "128Mi", "512Mi", 1, "5Gi"),
    TenantTier.PREMIUM: TierLimits("250m", "1000m", "256Mi", "1Gi", 2, "10Gi"),
}

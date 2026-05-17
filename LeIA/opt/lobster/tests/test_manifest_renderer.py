import pytest
import yaml
from jinja2 import UndefinedError

from lobster_agent.agent.mutations.manifests import ManifestRenderer
from lobster_agent.domain.tenants import TIER_LIMITS, TenantTier, TenantType


def test_renders_all_template_types() -> None:
    renderer = ManifestRenderer()
    for tenant_type in TenantType:
        docs = renderer.render(tenant_type, _context(tenant_type, TenantTier.FREE))
        assert docs
        assert docs[0]["kind"] == "Namespace"
        assert docs[0]["metadata"]["labels"]["saasphere.io/type"] == tenant_type.value


def test_tier_replicas_are_rendered() -> None:
    renderer = ManifestRenderer()
    docs = renderer.render(
        TenantType.STATIC_SITE,
        _context(TenantType.STATIC_SITE, TenantTier.PREMIUM),
    )
    deployments = [doc for doc in docs if doc["kind"] == "Deployment"]
    assert deployments[0]["spec"]["replicas"] == TIER_LIMITS[TenantTier.PREMIUM].replicas


def test_strict_undefined_raises() -> None:
    renderer = ManifestRenderer()
    with pytest.raises(UndefinedError):
        renderer.render(TenantType.WEB_APP, {"name": "x"})


def test_wordpress_passwords_differ() -> None:
    renderer = ManifestRenderer()
    first = renderer.render(TenantType.WORDPRESS, _context(TenantType.WORDPRESS, TenantTier.FREE))
    second = renderer.render(TenantType.WORDPRESS, _context(TenantType.WORDPRESS, TenantTier.FREE))
    first_secret = next(doc for doc in first if doc["kind"] == "Secret")
    second_secret = next(doc for doc in second if doc["kind"] == "Secret")
    assert first_secret["stringData"]["password"] != second_secret["stringData"]["password"]


def test_rendered_output_parses_as_yaml() -> None:
    renderer = ManifestRenderer()
    template = renderer.env.get_template("static_site.yaml.j2")
    text = template.render(**_context(TenantType.STATIC_SITE, TenantTier.BASIC))
    docs = list(yaml.safe_load_all(text))
    assert any(doc["kind"] == "Ingress" for doc in docs)


def _context(tenant_type: TenantType, tier: TenantTier) -> dict[str, object]:
    return {
        "name": "tenant-x",
        "tier": tier.value,
        "limits": TIER_LIMITS[tier],
        "hostname": "tenant-x.saasphere.local",
        "image": "nginx:alpine",
        "port": 8080,
        "env": {"A": "B"},
        "owner": "admin",
        "admin_email": "admin@example.com" if tenant_type == TenantType.WORDPRESS else None,
    }

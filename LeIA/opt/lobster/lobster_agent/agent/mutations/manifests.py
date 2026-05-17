import secrets
from pathlib import Path
from typing import Any, cast

import jinja2
import yaml

from lobster_agent.domain.tenants import TenantType


class ManifestRenderer:
    def __init__(self, templates_dir: Path = Path("lobster_agent/manifests")) -> None:
        self.env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(templates_dir),
            autoescape=False,
            undefined=jinja2.StrictUndefined,
        )

    def render(self, tenant_type: TenantType, context: dict[str, Any]) -> list[dict[str, Any]]:
        template = self.env.get_template(f"{tenant_type.value}.yaml.j2")
        render_context = dict(context)
        if tenant_type == TenantType.WORDPRESS and "db_password" not in render_context:
            render_context["db_password"] = self.generate_db_password()
        if tenant_type == TenantType.WORDPRESS and "quota_limits" not in render_context:
            limits = render_context["limits"]
            render_context["quota_limits"] = {
                "cpu_request": _double_quantity(str(limits.cpu_request)),
                "cpu_limit": _double_quantity(str(limits.cpu_limit)),
                "memory_request": _double_quantity(str(limits.memory_request)),
                "memory_limit": _double_quantity(str(limits.memory_limit)),
                "storage": _double_quantity(str(limits.storage)),
            }
        text = template.render(**render_context)
        documents = [doc for doc in yaml.safe_load_all(text) if doc is not None]
        resources: list[dict[str, Any]] = []
        for document in documents:
            if not isinstance(document, dict):
                raise ValueError("rendered manifest document must be a YAML object")
            resources.append(cast(dict[str, Any], document))
        return resources

    @staticmethod
    def generate_db_password() -> str:
        return secrets.token_urlsafe(24)


def _double_quantity(value: str) -> str:
    for suffix in ("Mi", "Gi", "m"):
        if value.endswith(suffix):
            amount = int(value[: -len(suffix)])
            return f"{amount * 2}{suffix}"
    if value.isdigit():
        return str(int(value) * 2)
    return value

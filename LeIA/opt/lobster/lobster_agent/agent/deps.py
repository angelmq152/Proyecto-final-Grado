from dataclasses import dataclass
from typing import TYPE_CHECKING

from lobster_agent.clients.alertmanager import AlertmanagerClient
from lobster_agent.clients.k8s import K8sClient
from lobster_agent.clients.loki import LokiClient
from lobster_agent.clients.prometheus import PrometheusClient
from lobster_agent.persistence.repositories import (
    ActionRepository,
    AgentStateRepository,
    DecisionRepository,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from lobster_agent.agent.approvals import ApprovalManager
    from lobster_agent.agent.mutations import MutationContext
    from lobster_agent.persistence.repositories import ToolRequestRepository
    from lobster_agent.telegram.notifier import TelegramNotifier


@dataclass
class AgentDeps:
    prometheus: PrometheusClient
    loki: LokiClient
    k8s: K8sClient
    alertmanager: AlertmanagerClient
    decisions_repo: DecisionRepository
    approval_manager: "ApprovalManager | None" = None
    action_repo_factory: "Callable[[], Awaitable[ActionRepository]] | None" = None
    agent_state_repo_factory: "Callable[[], Awaitable[AgentStateRepository]] | None" = None
    tool_request_repo_factory: "Callable[[], Awaitable[ToolRequestRepository]] | None" = None
    mutation_context: "MutationContext | None" = None
    notifier: "TelegramNotifier | None" = None
    current_case_use: str = ""

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol

from lobster_agent.agent.approvals import ApprovalRequest
from lobster_agent.domain.severity import ActionSeverity
from lobster_agent.persistence.models import Action, ActionStatus, ApprovalStatus
from lobster_agent.persistence.repositories import ActionRepository


class PolicyModule(Protocol):
    def validate(
        self,
        action_type: str,
        namespace: str,
        manifest: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> Any: ...


@dataclass(frozen=True)
class ActionResult:
    action_id: str
    status: ActionStatus
    message: str
    data: dict[str, Any] | None = None


ActionRepoFactory = Callable[[], Awaitable[ActionRepository]]


class MutationContext:
    """Common execution envelope for mutation tools."""

    def __init__(
        self,
        action_repo_factory: ActionRepoFactory,
        approval_manager: Any,
        policy_module: PolicyModule,
        notifier: Any,
        dry_run_default: bool,
        enforce_resource_limits: bool = True,
    ) -> None:
        self._action_repo_factory = action_repo_factory
        self._approval_manager = approval_manager
        self._policy_module = policy_module
        self._notifier = notifier
        self._dry_run_default = dry_run_default
        self._enforce_resource_limits = enforce_resource_limits

    def set_dry_run(self, enabled: bool) -> None:
        self._dry_run_default = enabled

    async def execute(
        self,
        action_type: str,
        namespace: str,
        target: str,
        payload: dict[str, Any],
        manifest: dict[str, Any] | None,
        executor: Callable[[], Awaitable[Any]],
        dry_run_override: bool | None = None,
        severity_override: ActionSeverity | None = None,
    ) -> ActionResult:
        repo = await self._action_repo_factory()
        policy_context = {
            "target": target,
            "enforce_resource_limits": self._enforce_resource_limits,
            **payload,
        }
        decision = self._policy_module.validate(
            action_type,
            namespace,
            manifest,
            policy_context,
        )
        severity = severity_override or _severity(decision.severity)
        dry_run = self._dry_run_default if dry_run_override is None else dry_run_override

        if not bool(decision.allowed):
            action = await repo.create(
                Action(
                    action_type=action_type,
                    namespace=namespace,
                    target=target,
                    severity=ActionSeverity.FORBIDDEN.value,
                    status=ActionStatus.ABORTED_POLICY.value,
                    payload=json.dumps(payload, sort_keys=True),
                    result=json.dumps(
                        {
                            "reason": str(decision.reason),
                            "violations": list(decision.violations),
                        },
                        sort_keys=True,
                    ),
                    dry_run=dry_run,
                )
            )
            return ActionResult(
                action_id=action.id,
                status=ActionStatus.ABORTED_POLICY,
                message=str(decision.reason),
                data={"violations": list(decision.violations)},
            )

        action = await repo.create(
            Action(
                action_type=action_type,
                namespace=namespace,
                target=target,
                severity=severity.value,
                status=ActionStatus.PENDING.value,
                payload=json.dumps(payload, sort_keys=True),
                dry_run=dry_run,
            )
        )

        if severity != ActionSeverity.AUTONOMOUS:
            await repo.update_status(action.id, ActionStatus.AWAITING_APPROVAL)
            if self._approval_manager is None:
                action = await repo.update_status(
                    action.id,
                    ActionStatus.REJECTED,
                    {"error": "approval manager unavailable"},
                )
                return ActionResult(
                    action_id=action.id,
                    status=ActionStatus.REJECTED,
                    message="approval manager unavailable",
                    data={"error": "approval manager unavailable"},
                )

            approval = await self._approval_manager.request_approval(
                ApprovalRequest(
                    case_use=str(payload.get("case_use", "mutation")),
                    action_type=action_type,
                    action_payload=payload,
                    severity=_approval_severity(severity),
                    tenant_namespace=namespace,
                    related_decision_id=_optional_str(payload.get("decision_id")),
                )
            )
            action = await repo.set_approval_id(action.id, approval.id)

            if approval.status == ApprovalStatus.PENDING and hasattr(
                self._approval_manager, "wait_for_decision"
            ):
                approval = await self._approval_manager.wait_for_decision(approval.id)

            if approval.status != ApprovalStatus.APPROVED:
                action = await repo.update_status(
                    action.id,
                    ActionStatus.REJECTED,
                    {
                        "approval_id": approval.id,
                        "approval_status": approval.status.value,
                        "reason": approval.decision_reason,
                    },
                )
                return ActionResult(
                    action_id=action.id,
                    status=ActionStatus.REJECTED,
                    message="approval rejected",
                    data={"approval_id": approval.id, "approval_status": approval.status.value},
                )
            await repo.update_status(
                action.id,
                ActionStatus.APPROVED,
                {"approval_id": approval.id},
            )

        if dry_run:
            action = await repo.update_status(
                action.id,
                ActionStatus.ABORTED_DRY_RUN,
                {"planned_manifest": manifest, "payload": payload},
            )
            return ActionResult(
                action_id=action.id,
                status=ActionStatus.ABORTED_DRY_RUN,
                message="dry run; mutation skipped",
                data={"planned_manifest": manifest, "payload": payload},
            )

        await repo.update_status(action.id, ActionStatus.RUNNING)
        try:
            raw_result = await executor()
        except Exception as exc:
            action = await repo.update_status(
                action.id,
                ActionStatus.FAILED,
                {"error": str(exc), "type": type(exc).__name__},
            )
            return ActionResult(
                action_id=action.id,
                status=ActionStatus.FAILED,
                message=str(exc),
                data={"error": str(exc), "type": type(exc).__name__},
            )

        result = _result_data(raw_result)
        action = await repo.update_status(action.id, ActionStatus.COMPLETED, result)
        return ActionResult(
            action_id=action.id,
            status=ActionStatus.COMPLETED,
            message="completed",
            data=result,
        )


def _severity(value: object) -> ActionSeverity:
    if isinstance(value, ActionSeverity):
        return value
    if isinstance(value, str):
        return ActionSeverity(value)
    raise TypeError(f"unsupported action severity: {value!r}")


def _approval_severity(severity: ActionSeverity) -> Any:
    from lobster_agent.persistence.models import ApprovalSeverity

    if severity == ActionSeverity.CRITICAL:
        return ApprovalSeverity.CRITICAL
    return ApprovalSeverity.NORMAL


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _result_data(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {"result": value}

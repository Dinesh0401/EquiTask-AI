"""Validation gate for agent outputs.

Implements the contract from AGENT_CONTRACTS.md::

    agent_output -> schema validation -> policy validation ->
    (human approval if consequential) -> service call

Any invalid output writes an AgentRun with status INVALID_OUTPUT and raises;
it never reaches the state machine.

No novelty is claimed; this is a deterministic, configurable gate that wraps
agent side effects behind hard constraints.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from pydantic import BaseModel

from .base import AgentRunError, BaseAgent, InvalidOutputError, PendingApprovalError


class GateStage(str, Enum):
    SCHEMA = "schema"
    POLICY = "policy"
    APPROVAL = "approval"
    SERVICE = "service"


@dataclass(frozen=True)
class GateResult:
    """Outcome of a single gate evaluation."""

    stage: GateStage
    passed: bool
    reason: str | None = None
    output: Any = None


class PolicyRule:
    """A single hard constraint evaluated against an agent output.

    Attributes:
        name: Stable reason code emitted when the rule fails.
        check: Callable ``(output, agent, context) -> bool`` returning True
            when the output satisfies the rule.
        message: Human-readable explanation of the requirement.
        consequential: If True, a failure blocks the service call and is
            reported as invalid output rather than merely logged.
    """

    def __init__(
        self,
        name: str,
        check: Callable[[Any, "BaseAgent", dict[str, Any] | None], bool],
        *,
        message: str = "",
        consequential: bool = True,
    ) -> None:
        self.name = name
        self.check = check
        self.message = message
        self.consequential = consequential

    def evaluate(self, output: Any, agent: "BaseAgent", context: dict[str, Any] | None = None) -> bool:
        try:
            return bool(self.check(output, agent, context))
        except Exception:  # pragma: no cover - defensive; rule errors fail closed
            return False


class ValidationGate:
    """Composes schema validation, policy rules, optional approval, and a service call.

    The gate is the single chokepoint through which every agent output must
    pass before a side effect is permitted. It fails closed: any rule failure
    raises InvalidOutputError so the agent records INVALID_OUTPUT and performs
    no state change.
    """

    def __init__(
        self,
        *,
        policy_rules: list[PolicyRule] | None = None,
        require_approval_for: frozenset[str] | None = None,
        service: Callable[[Any, "Agent", dict[str, Any] | None], Any] | None = None,
        auto_approve: bool = False,
    ) -> None:
        self.policy_rules: list[PolicyRule] = list(policy_rules or [])
        self.require_approval_for = require_approval_for or frozenset()
        self.service = service
        self.auto_approve = auto_approve

    def add_rule(self, rule: PolicyRule) -> None:
        self.policy_rules.append(rule)

    def validate(
        self,
        output: Any,
        agent: "BaseAgent",
        input: Any | None = None,
        context: dict[str, Any] | None = None,
    ) -> Any:
        """Run the full gate and return ``output`` if all stages pass.

        Raises:
            InvalidOutputError: if schema, policy, or service validation fails.
            PendingApprovalError: if a consequential action requires human
                approval and auto-approval is disabled.
        """
        context = context or {}
        context = dict(context)

        # 1. Schema validation: output must be a valid Pydantic model instance.
        if isinstance(output, BaseModel):
            try:
                type(output).model_validate(output)
            except Exception as exc:  # noqa: BLE001
                raise InvalidOutputError(f"schema validation failed: {exc}") from exc

        # 2. Policy validation: every registered rule must pass.
        for rule in self.policy_rules:
            if not rule.evaluate(output, agent, context):
                reason = rule.message or f"policy rule '{rule.name}' failed"
                raise InvalidOutputError(f"policy validation failed ({rule.name}): {reason}")

        # 3. Human approval if consequential.
        action = context.get("action", "")
        if action in self.require_approval_for and not self.auto_approve:
            raise PendingApprovalError(
                f"consequential action '{action}' requires human approval before service call"
            )

        # 4. Service call (side effect). Only reached when all prior stages pass.
        if self.service is not None:
            try:
                return self.service(output, agent, context)
            except Exception as exc:  # noqa: BLE001
                raise InvalidOutputError(f"service call failed: {exc}") from exc

        return output


# ---------------------------------------------------------------------------
# Reusable policy rules
# ---------------------------------------------------------------------------


def _force_assign_flagged(output: Any) -> bool:
    """True if output carries a force_assign=true signal (model or plain object)."""
    if isinstance(output, BaseModel):
        data = output.model_dump()
        if data.get("force_assign") is True:
            return True
        if "force_assign" in output.model_fields_set:
            return True
    return getattr(output, "force_assign", None) is True


def no_force_assign_rule() -> PolicyRule:
    """Reject outputs that attempt to force-assign a volunteer (agent overreach)."""

    def check(output: Any, agent: "BaseAgent", context: dict[str, Any] | None = None) -> bool:
        return not _force_assign_flagged(output)

    return PolicyRule(
        name="NO_FORCE_ASSIGN",
        check=check,
        message="Agents may not set force_assign=true; assignment is decided by consent and the state machine.",
        consequential=True,
    )


def no_private_volunteer_data_rule() -> PolicyRule:
    """Reject explanations that expose another volunteer's private attributes."""

    def check(output: Any, agent: Agent, context: dict[str, Any] | None = None) -> bool:
        text = ""
        if isinstance(output, BaseModel):
            text = " ".join(str(v) for v in output.model_dump().values() if isinstance(v, str))
        elif isinstance(output, str):
            text = output
        forbidden = ("email", "phone", "address", "preference", "proficiency", "capacity_hours")
        lowered = text.lower()
        return not any(token in lowered for token in forbidden)

    return PolicyRule(
        name="NO_PRIVATE_VOLUNTEER_DATA",
        check=check,
        message="Explanations must not expose other volunteers' private data.",
        consequential=True,
    )


def no_unverified_guarantee_rule() -> PolicyRule:
    """Reject outputs that claim fairness or performance guarantees not verified."""

    GUARANTEE_TOKENS = ("guaranteed", "guarantee", "always", "optimal", "provably fair", "certain")

    def check(output: Any, agent: Agent, context: dict[str, Any] | None = None) -> bool:
        text = ""
        if isinstance(output, BaseModel):
            text = " ".join(str(v) for v in output.model_dump().values() if isinstance(v, str))
        elif isinstance(output, str):
            text = output
        lowered = text.lower()
        return not any(token in lowered for token in GUARANTEE_TOKENS)

    return PolicyRule(
        name="NO_UNVERIFIED_GUARANTEE",
        check=check,
        message="Agents must not claim unverified fairness or performance guarantees.",
        consequential=True,
    )


def no_publish_without_approval_rule() -> PolicyRule:
    """Reject task-intake outputs that attempt to publish a task authoritatively."""

    def check(output: Any, agent: Agent, context: dict[str, Any] | None = None) -> bool:
        if isinstance(output, BaseModel):
            data = output.model_dump()
            if data.get("status") == "published" or data.get("publish") is True:
                return False
        return True

    return PolicyRule(
        name="NO_PUBLISH_WITHOUT_APPROVAL",
        check=check,
        message="Task intake may only produce drafts; publishing requires organization approval.",
        consequential=True,
    )

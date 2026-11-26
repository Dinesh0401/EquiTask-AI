"""Recovery Agent (Contract E).

Takes a :class:`DisruptionEvent` and the current state and produces a
:class:`RepairDiff`: a proposed diff of kept, released, and newly proposed
commitments. The agent never modifies accepted commitments silently — every
change is an explicit, reviewable diff.

Forbidden (per AGENT_CONTRACTS.md):
* modify accepted commitments silently
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from ..allocation.repair import build_repair_plan
from ..schemas import AllocationProblem
from .base import (
    AgentConfig,
    AgentStatus,
    AgentType,
    BaseAgent,
    InvalidOutputError,
    PermissionScope,
)
from .validator import PolicyRule, ValidationGate


class DisruptionEvent(BaseModel):
    """A disruption to an existing commitment."""

    event_type: str = Field(..., pattern="^(WITHDRAWAL|DEADLINE_CHANGE|NEW_TASK)$")
    assignment_id: str | None = Field(default=None, max_length=128)
    task_id: str | None = Field(default=None, max_length=128)
    occurred_at: datetime
    note: str | None = Field(default=None, max_length=1000)


class RecoveryInput(BaseModel):
    """Typed input: the disruption plus the current allocation state."""

    disruption: DisruptionEvent
    current_state: AllocationProblem


class RepairDiff(BaseModel):
    """A proposed diff, not a mutation.

    ``kept`` commitments are frozen; ``released`` commitments are explicitly
    flagged for reconfirmation; ``proposed`` are new solver proposals to be
    offered through consent.
    """

    event_type: str
    affected_volunteer_id: str | None = None
    affected_task_id: str | None = None
    kept: list[dict[str, str]] = Field(default_factory=list)
    released: list[dict[str, str]] = Field(default_factory=list)
    proposed: list[dict[str, str]] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    note: str = "Accepted commitments are frozen unless reconfirmed."
    requires_reconfirmation: bool = Field(default=False)


class RecoveryAgent(BaseAgent[RecoveryInput, RepairDiff]):
    """Computes a repair diff without silently modifying commitments.

    Accepted commitments are frozen. Only commitments affected by the
    disruption are released, and only after explicit flagging; new proposals
    require volunteer consent before activation.
    """

    agent_type = AgentType.RECOVERY
    input_model = RecoveryInput
    output_model = RepairDiff

    @classmethod
    def _default_scope(cls) -> PermissionScope:
        return PermissionScope(
            agent_type=AgentType.RECOVERY,
            allowed_actions=frozenset({"propose_repair_diff"}),
            forbidden_actions=frozenset({"modify_accepted_commitments_silently"}),
            requires_human_approval=frozenset({"apply_repair"}),
            consequential_actions=frozenset({"apply_repair"}),
        )

    def __init__(
        self,
        *,
        permission_scope: PermissionScope | None = None,
        config: AgentConfig | None = None,
        store=None,
        gate=None,
    ) -> None:
        super().__init__(
            permission_scope=permission_scope,
            config=config,
            store=store,
            gate=gate,
        )
        if gate is None:
            self.gate = ValidationGate(
                policy_rules=[
                    PolicyRule(
                        name="NO_SILENT_COMMITMENT_MODIFICATION",
                        check=self._no_silent_modification,
                        message="Accepted commitments must not be silently modified; every release is explicit.",
                        consequential=True,
                    ),
                    PolicyRule(
                        name="REPAIR_IS_A_DIFF",
                        check=self._is_a_diff,
                        message="The recovery agent must output a diff, not an applied state change.",
                        consequential=True,
                    ),
                ],
                service=self._apply_service,
                auto_approve=False,
            )

    def _execute(self, input: RecoveryInput) -> RepairDiff:
        """Compute a repair diff from the disruption and current state.

        Uses the deterministic repair engine (side-effect-free) to freeze
        accepted work and solve only residual demand. No commitment is
        modified here; the result is a proposed diff.
        """
        problem = input.current_state
        disruption = input.disruption

        affected_volunteer: str | None = None
        affected_task: str | None = None
        # For a WITHDRAWAL, infer the affected volunteer/task from the assignment
        # locked in the problem if not directly provided.
        for locked in problem.locked_assignments:
            if disruption.assignment_id and str(locked.get("assignment_id")) == str(disruption.assignment_id):
                affected_volunteer = str(locked.get("volunteer_id", ""))
                affected_task = str(locked.get("task_id", ""))
                break
        if not affected_volunteer:
            affected_volunteer = disruption.assignment_id  # best effort
        affected_task = affected_task or disruption.task_id

        plan = build_repair_plan(problem, affected_volunteer, affected_task)

        proposed = [
            {
                "volunteer_id": p.volunteer_id,
                "task_id": p.task_id,
                "action": "propose",
            }
            for p in plan.proposals.proposals
        ] if plan.proposals else []

        return RepairDiff(
            event_type=disruption.event_type,
            affected_volunteer_id=affected_volunteer or None,
            affected_task_id=affected_task or None,
            kept=plan.kept,
            released=plan.released,
            proposed=proposed,
            reason_codes=list(plan.reason_codes),
            note=plan.note,
            requires_reconfirmation=bool(plan.released),
        )

    # ------------------------------------------------------------------
    # Policy checks (wired behind the validation gate).
    # ------------------------------------------------------------------

    @staticmethod
    def _no_silent_modification(
        output: Any, agent: "RecoveryAgent", context: dict[str, Any] | None = None
    ) -> bool:
        if not isinstance(output, RepairDiff):
            return False
        # A release without an explicit note/reason is treated as silent.
        if output.released and not output.requires_reconfirmation:
            return False
        if output.released and "silent" in output.note.lower():
            return False
        return True

    @staticmethod
    def _is_a_diff(
        output: Any, agent: "RecoveryAgent", context: dict[str, Any] | None = None
    ) -> bool:
        return isinstance(output, RepairDiff)

    @staticmethod
    def _apply_service(
        output: Any, agent: "RecoveryAgent", context: dict[str, Any] | None = None
    ) -> Any:
        # Applying a repair is consequential and requires coordinator/human
        # approval. The service itself performs no commitment mutation; it
        # only returns the validated diff for review.
        if not isinstance(output, RepairDiff):
            raise InvalidOutputError("service expects a RepairDiff")
        return output


__all__ = ["DisruptionEvent", "RecoveryInput", "RepairDiff", "RecoveryAgent"]

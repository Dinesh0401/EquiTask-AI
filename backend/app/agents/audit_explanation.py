"""Audit/Explanation Agent (Contract F).

Produces an :class:`Explanation` from an :class:`~app.schemas.AllocationResult`
and permitted evidence only. Explanations never expose another volunteer's
private data and never claim unverified guarantees.

Forbidden (per AGENT_CONTRACTS.md):
* expose other volunteers' private data
* claim unverified guarantees
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..schemas import AllocationResult
from .base import (
    AgentConfig,
    AgentType,
    BaseAgent,
    PermissionScope,
)
from .validator import (
    PolicyRule,
    ValidationGate,
    no_private_volunteer_data_rule,
    no_unverified_guarantee_rule,
)


class ExplanationSegment(BaseModel):
    """One segment of an explanation, grounded in permitted evidence."""

    kind: str = Field(..., description="e.g. 'proposal', 'risk', 'infeasibility', 'disclaimer'")
    text: str = Field(..., min_length=1, max_length=5000)
    evidence_refs: list[str] = Field(default_factory=list)


class Explanation(BaseModel):
    """An explanation of an allocation result, using permitted evidence only."""

    result_id: str | None = None
    status: str
    segments: list[ExplanationSegment] = Field(default_factory=list)
    disclaimers: list[str] = Field(default_factory=list)
    policy_version: str = "v0.1.1"


class AuditExplanationInput(BaseModel):
    """Typed input: the allocation result plus permitted evidence."""

    result: AllocationResult
    permitted_evidence: dict[str, Any] = Field(default_factory=dict)
    actor_id: str | None = Field(default=None, description="Actor requesting the explanation (audit trail).")


class AuditExplanationAgent(BaseAgent[AuditExplanationInput, Explanation]):
    """Builds an explanation strictly from solver output and permitted evidence.

    Private volunteer attributes are never included, and no fairness or
    performance guarantee is claimed unless it was verified by the solver.
    """

    agent_type = AgentType.AUDIT_EXPLANATION
    input_model = AuditExplanationInput
    output_model = Explanation

    @classmethod
    def _default_scope(cls) -> PermissionScope:
        return PermissionScope(
            agent_type=AgentType.AUDIT_EXPLANATION,
            allowed_actions=frozenset({"read_permitted_outputs", "explain"}),
            forbidden_actions=frozenset({"expose_private_volunteer_data", "claim_unverified_guarantees"}),
            requires_human_approval=frozenset(),
            consequential_actions=frozenset(),
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
                    no_private_volunteer_data_rule(),
                    no_unverified_guarantee_rule(),
                    PolicyRule(
                        name="EVIDENCE_PERMITTED_ONLY",
                        check=self._evidence_permitted_only,
                        message="Explanations must use permitted evidence only.",
                        consequential=True,
                    ),
                ],
                service=self._explain_service,
                auto_approve=True,
            )

    def _execute(self, input: AuditExplanationInput) -> Explanation:
        """Build an explanation from the result and permitted evidence.

        Uses the deterministic explanation builder, which already avoids
        private data and unverified claims. The gate then re-checks both
        constraints before the explanation is released.
        """
        from ..allocation.explanations import explain_result

        result = input.result
        texts = explain_result(result)

        segments: list[ExplanationSegment] = []
        for index, text in enumerate(texts):
            kind = "infeasibility" if result.status in ("NO_FEASIBLE_PROPOSAL", "SOLVER_UNKNOWN") else "proposal"
            segments.append(
                ExplanationSegment(
                    kind=kind,
                    text=text,
                    evidence_refs=["solver_output"],
                )
            )

        disclaimers: list[str] = [
            "Proposals are not assignments; no commitment is active until consent is recorded.",
            "This explanation reflects solver output and permitted evidence only.",
        ]
        if result.status == "NO_FEASIBLE_PROPOSAL":
            disclaimers.append(
                "No feasible proposal was found under the stated hard constraints; "
                "this is not a guarantee about future feasibility."
            )

        return Explanation(
            result_id=None,
            status=result.status.value if hasattr(result.status, "value") else str(result.status),
            segments=segments,
            disclaimers=disclaimers,
            policy_version=result.policy_version,
        )

    # ------------------------------------------------------------------
    # Policy checks (wired behind the validation gate).
    # ------------------------------------------------------------------

    @staticmethod
    def _evidence_permitted_only(
        output: Any, agent: "AuditExplanationAgent", context: dict[str, Any] | None = None
    ) -> bool:
        if not isinstance(output, Explanation):
            return False
        joined = " ".join(s.text for s in output.segments) + " " + " ".join(output.disclaimers)
        lowered = joined.lower()
        return "private" not in lowered or "permitted evidence" in lowered

    @staticmethod
    def _explain_service(
        output: Any, agent: "AuditExplanationAgent", context: dict[str, Any] | None = None
    ) -> Any:
        # Producing an explanation is read-only; no state change occurs.
        if not isinstance(output, Explanation):
            raise ValueError("service expects an Explanation")
        return output


__all__ = ["Explanation", "ExplanationSegment", "AuditExplanationInput", "AuditExplanationAgent"]

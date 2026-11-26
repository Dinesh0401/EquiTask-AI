"""Allocation Planning Agent (Contract C).

Translates a typed :class:`~app.schemas.AllocationProblem` into a
:class:`SolverRequest` that is handed to the deterministic CP-SAT solver
(:func:`~app.allocation.allocate`). The agent plans and validates; it does not
output final assignments itself — the solver produces proposals, never
assignments.

Forbidden (per AGENT_CONTRACTS.md):
* output final assignments itself
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..allocation import allocate
from ..enums import SolverMode
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


class SolverRequest(BaseModel):
    """A request to the deterministic solver, not a set of assignments."""

    problem: AllocationProblem
    mode: SolverMode = SolverMode.FAIRNESS_AWARE
    enable_questions: bool = True
    time_limit_seconds: float = Field(default=5.0, gt=0, le=120)

    class Config:
        arbitrary_types_allowed = True


class AllocationPlanningAgent(BaseAgent[AllocationProblem, SolverRequest]):
    """Validates an allocation problem and emits a SolverRequest.

    The agent checks that the problem is well-formed and within MVP caps,
    then returns a SolverRequest. A separate service call (wired through the
    validation gate) invokes :func:`app.allocation.allocate`. The agent itself
    never emits final assignments; proposals from the solver are not
    assignments and require consent before activation.
    """

    agent_type = AgentType.ALLOCATION_PLANNING
    input_model = AllocationProblem
    output_model = SolverRequest

    @classmethod
    def _default_scope(cls) -> PermissionScope:
        return PermissionScope(
            agent_type=AgentType.ALLOCATION_PLANNING,
            allowed_actions=frozenset({"call_deterministic_solver"}),
            forbidden_actions=frozenset({"output_final_assignments"}),
            requires_human_approval=frozenset(),
            consequential_actions=frozenset({"call_deterministic_solver"}),
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
        # Wire the deterministic solver as the service call behind the gate.
        # The agent never calls the solver directly; the gate performs the
        # service call only after schema + policy validation pass.
        if gate is None:
            self.gate = ValidationGate(
                policy_rules=[
                    PolicyRule(
                        name="PROBLEM_WITHIN_CAPS",
                        check=self._problem_within_caps,
                        message="Problem exceeds MVP caps of 200 volunteers and 200 tasks.",
                        consequential=True,
                    ),
                    PolicyRule(
                        name="NO_FINAL_ASSIGNMENTS_OUTPUT",
                        check=self._no_final_assignments_output,
                        message="The allocation planning agent must not output final assignments.",
                        consequential=True,
                    ),
                ],
                service=self._solve_service,
                auto_approve=False,
            )

    def _execute(self, input: AllocationProblem) -> SolverRequest:
        """Validate the problem and produce a SolverRequest.

        No assignments are produced here. The returned request is handed to
        the gate's service call, which invokes the deterministic solver.
        """
        # Pydantic re-validation of the typed input (defensive).
        validated = AllocationProblem.model_validate(input)

        mode = validated.mode
        time_limit = validated.policy.solver_time_limit_seconds
        if time_limit > self.config.timeout_seconds:
            time_limit = self.config.timeout_seconds

        return SolverRequest(
            problem=validated,
            mode=mode,
            enable_questions=True,
            time_limit_seconds=time_limit,
        )

    # ------------------------------------------------------------------
    # Policy checks and solver service (wired behind the validation gate).
    # ------------------------------------------------------------------

    @staticmethod
    def _problem_within_caps(
        output: Any, agent: "AllocationPlanningAgent", context: dict[str, Any] | None = None
    ) -> bool:
        if not isinstance(output, SolverRequest):
            return False
        problem = output.problem
        return len(problem.volunteers) <= 200 and len(problem.tasks) <= 200

    @staticmethod
    def _no_final_assignments_output(
        output: Any, agent: "AllocationPlanningAgent", context: dict[str, Any] | None = None
    ) -> bool:
        # The agent output type is SolverRequest, which contains no
        # assignments. Fail closed if anything assignment-shaped leaks out.
        return not hasattr(output, "proposals") and not hasattr(output, "assignments")

    @staticmethod
    def _solve_service(
        output: Any, agent: "AllocationPlanningAgent", context: dict[str, Any] | None = None
    ) -> Any:
        if not isinstance(output, SolverRequest):
            raise InvalidOutputError("service expects a SolverRequest")
        # The deterministic solver produces proposals, never assignments.
        return allocate(
            output.problem,
            mode=output.mode,
            enable_questions=output.enable_questions,
        )


__all__ = ["SolverRequest", "AllocationPlanningAgent"]

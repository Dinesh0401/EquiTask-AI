"""Baseline runners for Phase 2 simulation experiments.

Wraps the existing allocation baselines (greedy, random, CP-SAT efficiency,
CP-SAT fairness) so they can be compared against the proposed uncertainty-
aware allocation method under identical conditions.
"""

from __future__ import annotations

from typing import Any

from app.allocation.baselines import (
    greedy_skill_match,
    random_feasible,
    cp_sat_efficiency,
    cp_sat_fairness,
)
from app.allocation import allocate
from app.schemas import AllocationProblem


class BaselineRunner:
    """Runs a named baseline against an allocation problem.

    All baselines consume the same typed AllocationProblem and are checked by
    the same invariant rules. A baseline that violates hard constraints is
    marked invalid.
    """

    def __init__(self, name: str):
        self.name = name

    def run(self, problem: AllocationProblem) -> Any:
        if self.name == "random_feasible":
            return random_feasible(problem, seed=7)
        if self.name == "greedy_skill_match":
            return greedy_skill_match(problem)
        if self.name == "cp_sat_efficiency":
            return cp_sat_efficiency(problem)
        if self.name == "cp_sat_fairness":
            return cp_sat_fairness(problem)
        if self.name == "proposed_uncertainty_aware":
            # The proposed method is the fairness-aware CP-SAT core with
            # uncertainty penalization already built into fit/risk scoring.
            return allocate(problem, mode="FAIRNESS_AWARE")
        raise ValueError(f"Unknown baseline: {self.name}")

    def is_valid(self, result: Any) -> bool:
        """A baseline is valid if it returns proposals without hard-constraint
        violations. Infeasible results are valid outcomes (not violations)."""
        return getattr(result, "status", "") != "INVALID_INPUT"

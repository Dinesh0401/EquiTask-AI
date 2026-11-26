"""Metrics computation for Phase 2 simulation experiments.

All metrics are computed from deterministic simulation output. No results are
claimed; this is a measurement instrument only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Metrics:
    """Aggregated metrics for a single allocation run."""

    # Core feasibility.
    feasible_allocation_rate: float = 0.0
    constraint_violations: int = 0

    # Completion.
    expected_completion_value: float = 0.0
    realized_completion_value: float = 0.0
    completion_rate: float = 0.0

    # Fairness (from mathematical formulation).
    workload_unfairness: float = 0.0
    opportunity_unfairness: float = 0.0
    preference_satisfaction: float = 0.0
    newcomer_exclusion_rate: float = 0.0

    # Coordination.
    clarification_questions: int = 0
    clarification_burden: float = 0.0
    reassignment_disruption: float = 0.0
    disturbance_hours: float = 0.0
    recovery_latency_ms: float = 0.0

    # Solver.
    solver_runtime_ms: float = 0.0
    solver_status: str = ""
    optimality_gap: float | None = None

    # Composite.
    coordination_quality: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "feasible_allocation_rate": self.feasible_allocation_rate,
            "constraint_violations": self.constraint_violations,
            "expected_completion_value": self.expected_completion_value,
            "realized_completion_value": self.realized_completion_value,
            "completion_rate": self.completion_rate,
            "workload_unfairness": self.workload_unfairness,
            "opportunity_unfairness": self.opportunity_unfairness,
            "preference_satisfaction": self.preference_satisfaction,
            "newcomer_exclusion_rate": self.newcomer_exclusion_rate,
            "clarification_questions": self.clarification_questions,
            "clarification_burden": self.clarification_burden,
            "reassignment_disruption": self.reassignment_disruption,
            "disturbance_hours": self.disturbance_hours,
            "recovery_latency_ms": self.recovery_latency_ms,
            "solver_runtime_ms": self.solver_runtime_ms,
            "solver_status": self.solver_status,
            "optimality_gap": self.optimality_gap,
            "coordination_quality": self.coordination_quality,
        }


def compute_run_metrics(
    allocation_result: Any,
    scenario_volunteers: list[Any],
    scenario_tasks: list[Any],
) -> Metrics:
    """Compute metrics from a single allocation engine result."""
    m = Metrics()

    m.solver_status = getattr(allocation_result, "status", "UNKNOWN")
    metrics = getattr(allocation_result, "metrics", None)
    if metrics is not None:
        m.solver_runtime_ms = getattr(metrics, "solver_runtime_ms", 0.0)
        m.workload_unfairness = getattr(metrics, "workload_unfairness", 0)
        m.opportunity_unfairness = getattr(metrics, "opportunity_unfairness", 0)
        m.expected_completion_value = getattr(metrics, "expected_contribution", 0)
        m.optimality_gap = getattr(metrics, "optimality_gap", None)

    proposals = getattr(allocation_result, "proposals", []) or []
    m.feasible_allocation_rate = 1.0 if proposals or len(proposals) == 0 else 0.0
    m.constraint_violations = 0

    task_values = {t.id: t.value for t in scenario_tasks}
    total_value = 0.0
    for p in proposals:
        total_value += task_values.get(p.task_id, 0) * (p.fit_score / 100.0)
    m.expected_completion_value = total_value

    m.coordination_quality = (
        total_value
        - m.workload_unfairness / 1000.0
        - m.opportunity_unfairness / 1000.0
    )

    return m


def aggregate_metrics(run_metrics: list[Metrics]) -> dict[str, Any]:
    """Aggregate metrics across multiple simulation runs."""
    if not run_metrics:
        return {}

    def _field(name: str) -> list[float]:
        return [getattr(rm, name) for rm in run_metrics if getattr(rm, name) is not None]

    def _summary(values: list[float]) -> dict[str, float | None]:
        if not values:
            return {"mean": None, "min": None, "max": None, "count": 0}
        return {
            "mean": sum(values) / len(values),
            "min": min(values),
            "max": max(values),
            "count": len(values),
        }

    return {
        "n_runs": len(run_metrics),
        "feasible_allocation_rate": _summary(_field("feasible_allocation_rate")),
        "constraint_violations": _summary(_field("constraint_violations")),
        "expected_completion_value": _summary(_field("expected_completion_value")),
        "workload_unfairness": _summary(_field("workload_unfairness")),
        "opportunity_unfairness": _summary(_field("opportunity_unfairness")),
        "preference_satisfaction": _summary(_field("preference_satisfaction")),
        "clarification_questions": _summary(_field("clarification_questions")),
        "reassignment_disruption": _summary(_field("reassignment_disruption")),
        "solver_runtime_ms": _summary(_field("solver_runtime_ms")),
        "coordination_quality": _summary(
            [rm.coordination_quality for rm in run_metrics if rm.coordination_quality is not None]
        ),
    }

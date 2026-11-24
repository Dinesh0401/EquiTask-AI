from __future__ import annotations

from dataclasses import dataclass, field

from ..schemas import AllocationProblem, AllocationResult
from .engine import allocate
from .policy import version_metadata


@dataclass
class RepairPlan:
    kept: list[dict[str, str]] = field(default_factory=list)
    released: list[dict[str, str]] = field(default_factory=list)
    proposals: AllocationResult | None = None
    reason_codes: list[str] = field(default_factory=list)
    note: str = "No accepted commitment was silently modified."


def build_repair_plan(
    problem: AllocationProblem,
    affected_volunteer_id: str | None = None,
    affected_task_id: str | None = None,
) -> RepairPlan:
    """Freeze accepted work and solve only the residual demand.

    Capacity of the affected volunteer must already reflect the withdrawal in
    the typed problem. The returned plan is a diff, not a state mutation.
    """
    policy_version, _ = version_metadata()
    locked = [dict(a) for a in problem.locked_assignments]
    kept: list[dict[str, str]] = []
    released: list[dict[str, str]] = []
    for assignment in locked:
        is_affected = (affected_volunteer_id and assignment.get("volunteer_id") == affected_volunteer_id) and (
            affected_task_id is None or assignment.get("task_id") == affected_task_id
        )
        if is_affected:
            released.append(
                {
                    "volunteer_id": str(assignment.get("volunteer_id", "")),
                    "task_id": str(assignment.get("task_id", "")),
                }
            )
        else:
            kept.append(
                {
                    "volunteer_id": str(assignment.get("volunteer_id", "")),
                    "task_id": str(assignment.get("task_id", "")),
                }
            )

    residual = problem.model_copy(deep=True)
    residual.mode = "REPAIR"
    kept_keys = {(a["volunteer_id"], a["task_id"]) for a in kept}
    residual.locked_assignments = [
        a for a in residual.locked_assignments if (a.get("volunteer_id"), a.get("task_id")) in kept_keys
    ]
    result = allocate(residual, mode="REPAIR", enable_questions=False)
    return RepairPlan(
        kept=kept,
        released=released,
        proposals=result,
        reason_codes=result.reason_codes,
        note=f"Repair evaluated under {policy_version}; accepted commitments are frozen unless reconfirmed.",
    )

from __future__ import annotations

from collections import Counter

from ..schemas import AllocationProblem
from .candidate import CandidateSet, compute_overlap_pairs

REASON_TEXT = {
    "TASK_ORG_NOT_VERIFIED": "Organization is not verified; task cannot be published.",
    "TASK_NO_ACCEPTANCE_CRITERIA": "Task lacks acceptance criteria; cannot be allocated.",
    "TASK_DEADLINE_BEFORE_WINDOW_END": "Deadline precedes the stated work window end.",
    "TASK_UNKNOWN_DEPENDENCY": "Task references an unknown dependency.",
    "CONTACT_NOT_PERMITTED": "Volunteer has not permitted contact about opportunities.",
    "CAPACITY_EXHAUSTED": "Volunteer has no remaining agreed capacity.",
    "CONSENT_REFUSED": "Volunteer declined or withdrew; proposal is forbidden.",
    "PREFERENCE_AVOID": "Volunteer marked this task type as avoid.",
    "AVAILABILITY_FALSE": "Availability is explicitly false.",
    "SKILL_MISSING": "A mandatory skill was never reported; treated as unknown, not invented, and excluded from hard-safe candidates.",
    "SKILL_FALSE": "A mandatory skill is explicitly false.",
    "SKILL_INSUFFICIENT": "Known skill proficiency is below the mandatory minimum.",
    "NO_CANDIDATES": "No volunteer passed the hard gates for at least one task.",
    "CAPACITY_BOTTLENECK": "Candidate volunteers lack enough remaining capacity for the task effort.",
    "OVERLAP_CONFLICT": "Overlapping task windows prevent a single volunteer from covering required tasks.",
    "DEPENDENCY_CYCLE": "Task dependencies contain a cycle.",
    "UNSATISFIABLE_FAIRNESS": "Fairness target conflicts with hard constraints; no right or safety constraint was relaxed.",
    "SOLVER_TIMEOUT": "Solver stopped before proving feasibility or infeasibility; no assignment was created.",
    "LOCKED_CONFLICT": "Accepted commitments conflict with residual demand.",
}


def detect_cycles(problem: AllocationProblem) -> list[str]:
    task_ids = {t.id for t in problem.tasks}
    graph = {t.id: [d for d in t.dependencies if d in task_ids] for t in problem.tasks}
    visiting: set[str] = set()
    done: set[str] = set()
    cycles: list[str] = []

    def visit(node: str, path: list[str]) -> None:
        if node in visiting:
            cycles.append(" -> ".join(path + [node]))
            return
        if node in done:
            return
        visiting.add(node)
        for dep in graph.get(node, []):
            visit(dep, path + [node])
        visiting.remove(node)
        done.add(node)

    for node in graph:
        visit(node, [])
    return cycles


def diagnose(problem: AllocationProblem, candidates: CandidateSet) -> tuple[list[str], list[str]]:
    reason_codes: list[str] = []
    messages: list[str] = []

    cycles = detect_cycles(problem)
    if cycles:
        reason_codes.append("DEPENDENCY_CYCLE")
        messages.extend(f"Dependency cycle: {cycle}" for cycle in cycles)

    for task in problem.tasks:
        task_candidates = [c for c in candidates.candidates if c.task_id == task.id]
        if len(task_candidates) < task.max_assignees:
            reason_codes.append("NO_CANDIDATES")
            messages.append(f"Task {task.id}: only {len(task_candidates)} hard-safe candidate(s), need {task.max_assignees}.")
            if any(code in candidates.exclusions for code in ("CAPACITY_EXHAUSTED",)):
                reason_codes.append("CAPACITY_BOTTLENECK")
        if len(task_candidates) > 1 and len({c.volunteer_id for c in task_candidates}) < task.max_assignees:
            reason_codes.append("CAPACITY_BOTTLENECK")

    overlap_pairs = compute_overlap_pairs(problem.tasks)
    if overlap_pairs and len(problem.tasks) > 1 and not candidates.candidates:
        reason_codes.append("OVERLAP_CONFLICT")

    if problem.locked_assignments:
        locked_pairs = {(a.get("volunteer_id"), a.get("task_id")) for a in problem.locked_assignments}
        if any((c.volunteer_id, c.task_id) in locked_pairs for c in candidates.candidates):
            reason_codes.append("LOCKED_CONFLICT")

    for code, _count in Counter(reason_codes).items():
        if code not in REASON_TEXT:
            continue
    # Deduplicate while preserving order for deterministic output.
    ordered = list(dict.fromkeys(reason_codes))
    return ordered, [REASON_TEXT.get(code, code) for code in ordered]

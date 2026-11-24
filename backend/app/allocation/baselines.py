from __future__ import annotations

import random
import time

from ..schemas import AllocationProblem, AllocationResult, ProposalOut
from .candidate import build_candidates
from .engine import allocate
from .policy import version_metadata


def greedy_skill_match(problem: AllocationProblem) -> AllocationResult:
    """B3: highest fit first, with the same hard gates and capacity checks."""
    started = time.perf_counter()
    candidates = build_candidates(problem).candidates
    policy_version, solver_version = version_metadata()
    effort = {t.id: t.effort_hours for t in problem.tasks}
    remaining = {v.id: v.capacity_hours - v.committed_hours for v in problem.volunteers}
    covered: dict[str, int] = {t.id: 0 for t in problem.tasks}
    selected: set[tuple[str, str]] = set()

    ordered = sorted(candidates, key=lambda c: (-c.fit, c.task_id, c.volunteer_id))
    for candidate in ordered:
        task = next(t for t in problem.tasks if t.id == candidate.task_id)
        if covered[task.id] >= task.max_assignees:
            continue
        if remaining[candidate.volunteer_id] < effort[task.id]:
            continue
        selected.add((candidate.volunteer_id, candidate.task_id))
        covered[task.id] += 1
        remaining[candidate.volunteer_id] -= effort[task.id]

    complete = all(covered[t.id] >= t.max_assignees for t in problem.tasks if t.organization_verified)
    proposals = sorted(
        (
            ProposalOut(
                volunteer_id=c.volunteer_id,
                task_id=c.task_id,
                fit_score=c.fit,
                risk_score=round(c.risk, 4),
                reasons=["greedy_skill_match"],
            )
            for c in candidates
            if (c.volunteer_id, c.task_id) in selected
        ),
        key=lambda p: (p.task_id, p.volunteer_id),
    )
    return AllocationResult(
        status="OPTIMAL_PROPOSALS" if complete else "NO_FEASIBLE_PROPOSAL",
        proposals=proposals,
        reason_codes=[] if complete else ["NO_CANDIDATES"],
        messages=[] if complete else ["Greedy baseline could not cover all publishable tasks."],
        policy_version=policy_version,
        solver_version=solver_version + "/greedy",
        solver_status_raw=f"greedy_runtime_ms={(time.perf_counter() - started) * 1000:.3f}",
    )


def random_feasible(problem: AllocationProblem, seed: int) -> AllocationResult:
    """B1: random feasible assignment using candidate gates and capacity checks."""
    rng = random.Random(seed)
    candidates = build_candidates(problem).candidates
    policy_version, solver_version = version_metadata()
    effort = {t.id: t.effort_hours for t in problem.tasks}
    remaining = {v.id: v.capacity_hours - v.committed_hours for v in problem.volunteers}
    covered: dict[str, int] = {t.id: 0 for t in problem.tasks}
    selected: set[tuple[str, str]] = set()

    shuffled = list(candidates)
    rng.shuffle(shuffled)
    for candidate in shuffled:
        task = next(t for t in problem.tasks if t.id == candidate.task_id)
        if covered[task.id] >= task.max_assignees:
            continue
        if remaining[candidate.volunteer_id] < effort[task.id]:
            continue
        selected.add((candidate.volunteer_id, candidate.task_id))
        covered[task.id] += 1
        remaining[candidate.volunteer_id] -= effort[task.id]

    complete = all(covered[t.id] >= t.max_assignees for t in problem.tasks if t.organization_verified)
    proposals = sorted(
        (
            ProposalOut(
                volunteer_id=c.volunteer_id,
                task_id=c.task_id,
                fit_score=c.fit,
                risk_score=round(c.risk, 4),
                reasons=["random_feasible"],
            )
            for c in candidates
            if (c.volunteer_id, c.task_id) in selected
        ),
        key=lambda p: (p.task_id, p.volunteer_id),
    )
    return AllocationResult(
        status="OPTIMAL_PROPOSALS" if complete else "NO_FEASIBLE_PROPOSAL",
        proposals=proposals,
        reason_codes=[] if complete else ["NO_CANDIDATES"],
        policy_version=policy_version,
        solver_version=solver_version + f"/random-seed-{seed}",
    )


def cp_sat_efficiency(problem: AllocationProblem) -> AllocationResult:
    """B5: isolates contribution from fairness terms."""
    return allocate(problem, mode="EFFICIENCY")


def cp_sat_fairness(problem: AllocationProblem) -> AllocationResult:
    """B6: proposed deterministic core."""
    return allocate(problem, mode="FAIRNESS_AWARE")

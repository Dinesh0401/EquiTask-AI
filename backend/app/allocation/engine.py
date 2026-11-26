from __future__ import annotations

import time
from collections import defaultdict

from ortools.sat.python import cp_model

from ..enums import SolverMode, SolverStatus
from ..schemas import (
    AllocationMetrics,
    AllocationProblem,
    AllocationResult,
    ClarificationQuestion,
    ProposalOut,
)
from .candidate import Candidate, CandidateSet, build_candidates, compute_overlap_pairs
from .diagnostics import REASON_TEXT, diagnose, detect_cycles
from .metrics import expected_contribution, overhead_term, risk_term
from .policy import adaptive_time_limit, configure_solver, version_metadata

SCALE = 1000
HOUR_SCALE = 10  # tenths of an hour keep CP-SAT arithmetic integral


def _int(value: float) -> int:
    return int(round(value))


def _select_questions(
    problem: AllocationProblem, candidates: list[Candidate], task_values: dict[str, int]
) -> list[ClarificationQuestion]:
    grouped: dict[tuple[str, str], tuple[float, str | None]] = {}
    for candidate in candidates:
        task_value = task_values.get(candidate.task_id, 0)
        for field in candidate.unknown_fields:
            key = (candidate.volunteer_id, field)
            value = candidate.risk * candidate.fit * task_value / 1000.0
            existing = grouped.get(key)
            if existing is None or value > existing[0]:
                grouped[key] = (value, candidate.task_id)
    questions = [
        ClarificationQuestion(
            volunteer_id=vid,
            field=field,
            task_id=task_id,
            reason=f"{field} is UNKNOWN or STALE and affects allocation feasibility or fit.",
            burden=2 if field in ("availability", "skill") else 1,
            expected_value=round(value, 4),
        )
        for (vid, field), (value, task_id) in grouped.items()
    ]
    questions.sort(key=lambda q: (-q.expected_value, q.burden, q.volunteer_id, q.field))
    return questions[: problem.policy.max_questions_per_round]


def _failure(
    problem: AllocationProblem,
    candidates: CandidateSet,
    status: SolverStatus,
    reason_codes: list[str],
    messages: list[str],
    questions: list[ClarificationQuestion],
    elapsed_ms: float,
) -> AllocationResult:
    codes, text = diagnose(problem, candidates)
    merged = list(dict.fromkeys(reason_codes + codes))
    merged_text = list(dict.fromkeys(messages + text))
    policy_version, solver_version = version_metadata()
    return AllocationResult(
        status=status,
        questions=questions,
        reason_codes=merged,
        messages=merged_text,
        policy_version=policy_version,
        solver_version=solver_version,
    )


def allocate(
    problem: AllocationProblem,
    mode: SolverMode | None = None,
    enable_questions: bool = True,
) -> AllocationResult:
    """Solve a typed allocation problem. Proposals are never assignments."""
    started = time.perf_counter()
    mode = mode or problem.mode
    policy = problem.policy
    policy_version, solver_version = version_metadata()
    elapsed = lambda: (time.perf_counter() - started) * 1000  # noqa: E731

    cycles = detect_cycles(problem)
    if cycles:
        return _failure(
            problem,
            CandidateSet(),
            SolverStatus.NO_FEASIBLE_PROPOSAL,
            ["DEPENDENCY_CYCLE"],
            [f"Dependency cycle: {cycle}" for cycle in cycles],
            [],
            elapsed(),
        )

    candidate_set = build_candidates(problem)
    candidates = candidate_set.candidates
    task_values = {t.id: t.value for t in problem.tasks}
    questions = _select_questions(problem, candidates, task_values) if enable_questions else []

    publishable_tasks = [
        t
        for t in problem.tasks
        if t.organization_verified and t.acceptance_criteria_present and t.end_utc <= t.deadline_utc
    ]
    if not candidates or not publishable_tasks:
        return _failure(
            problem,
            candidate_set,
            SolverStatus.NO_FEASIBLE_PROPOSAL,
            ["NO_CANDIDATES"],
            [],
            questions,
            elapsed(),
        )

    model = cp_model.CpModel()
    x: dict[tuple[str, str], object] = {}
    for index, candidate in enumerate(sorted(candidates, key=lambda c: (c.task_id, c.volunteer_id))):
        key = (candidate.volunteer_id, candidate.task_id)
        x[key] = model.NewBoolVar(f"x_{index}_{candidate.volunteer_id}_{candidate.task_id}")

    candidates_by_task: dict[str, list[Candidate]] = defaultdict(list)
    candidates_by_volunteer: dict[str, list[Candidate]] = defaultdict(list)
    for candidate in candidates:
        candidates_by_task[candidate.task_id].append(candidate)
        candidates_by_volunteer[candidate.volunteer_id].append(candidate)

    # H3: cover required tasks exactly once; optional tasks are best-effort.
    for task in publishable_tasks:
        matching = [x[(c.volunteer_id, c.task_id)] for c in candidates_by_task.get(task.id, [])]
        if task.required:
            if len(matching) < task.max_assignees:
                return _failure(
                    problem,
                    candidate_set,
                    SolverStatus.NO_FEASIBLE_PROPOSAL,
                    ["NO_CANDIDATES"],
                    [f"Required task {task.id} has fewer hard-safe candidates than required assignees."],
                    questions,
                    elapsed(),
                )
            model.Add(sum(matching) == task.max_assignees)
        else:
            # Optional task: cover as many assignees as possible, up to max_assignees.
            model.Add(sum(matching) <= task.max_assignees)

    # H2: remaining capacity across all proposed tasks.
    effort_by_task = {t.id: _int(t.effort_hours * HOUR_SCALE) for t in problem.tasks}
    for volunteer in problem.volunteers:
        remaining = _int((volunteer.capacity_hours - volunteer.committed_hours) * HOUR_SCALE)
        terms = [
            effort_by_task[c.task_id] * x[(volunteer.id, c.task_id)]
            for c in candidates_by_volunteer.get(volunteer.id, [])
        ]
        model.Add(sum(terms) <= max(0, remaining))

    # H4: incompatible overlapping windows for the same volunteer.
    overlaps = compute_overlap_pairs(publishable_tasks)
    for a_id, b_id in sorted(overlaps):
        ids_a = {c.volunteer_id for c in candidates_by_task.get(a_id, [])}
        ids_b = {c.volunteer_id for c in candidates_by_task.get(b_id, [])}
        for vid in sorted(ids_a & ids_b):
            model.Add(x[(vid, a_id)] + x[(vid, b_id)] <= 1)

    # H5: dependencies.
    completed = set(problem.completed_task_ids)
    for task in publishable_tasks:
        for dep in task.dependencies:
            if dep in completed:
                continue
            dep_vars = [x[(c.volunteer_id, dep)] for c in candidates_by_task.get(dep, [])]
            for candidate in candidates_by_task.get(task.id, []):
                model.Add(x[(candidate.volunteer_id, task.id)] <= sum(dep_vars))

    # H9 / repair: accepted commitments are frozen unless explicitly permitted.
    disruption_terms: list[object] = []
    locked_pairs = {(a.get("volunteer_id"), a.get("task_id")): a for a in problem.locked_assignments}
    for (vid, tid), assignment in locked_pairs.items():
        if (vid, tid) not in x:
            continue
        if assignment.get("change_permitted") and assignment.get("reconfirmation_recorded"):
            break_cost = _int(assignment.get("break_cost", 1) * SCALE)
            z = model.NewBoolVar(f"z_{vid}_{tid}")
            model.Add(z + x[(vid, tid)] <= 1)
            disruption_terms.append(break_cost * z)
        else:
            model.Add(x[(vid, tid)] == 0)

    # Scaled workload utilization and absolute deviation from the cohort mean.
    util_vars: dict[str, object] = {}
    util_scaled_terms: list[object] = []
    n_volunteers = len(problem.volunteers)
    for volunteer in problem.volunteers:
        den = max(1, _int(volunteer.capacity_hours * HOUR_SCALE))
        committed = _int(volunteer.committed_hours * HOUR_SCALE)
        num = committed * SCALE + sum(
            effort_by_task[c.task_id] * SCALE * x[(volunteer.id, c.task_id)]
            for c in candidates_by_volunteer.get(volunteer.id, [])
        )
        util = model.NewIntVar(0, 10 * SCALE, f"util_{volunteer.id}")
        model.Add(util * den <= num)
        model.Add(util * den >= num - den + 1)
        util_vars[volunteer.id] = util
        util_scaled_terms.append(util)

    sum_util = sum(util_scaled_terms)
    workload_deviations: list[object] = []
    for volunteer in problem.volunteers:
        dev = model.NewIntVar(0, 10 * SCALE, f"wdev_{volunteer.id}")
        model.Add(n_volunteers * dev >= n_volunteers * util_vars[volunteer.id] - sum_util)
        model.Add(n_volunteers * dev >= sum_util - n_volunteers * util_vars[volunteer.id])
        workload_deviations.append(dev)

    # Opportunity fairness among eligible volunteers, history adjusted.
    opp_vars: dict[str, object] = {}
    opp_deviations: list[object] = []
    for volunteer in problem.volunteers:
        eligible_count = len(candidates_by_volunteer.get(volunteer.id, []))
        den = max(1, volunteer.history_offers + eligible_count)
        num = SCALE * volunteer.history_offers + SCALE * sum(
            x[(volunteer.id, c.task_id)] for c in candidates_by_volunteer.get(volunteer.id, [])
        )
        opp = model.NewIntVar(0, SCALE * (volunteer.history_offers + eligible_count + 1), f"opp_{volunteer.id}")
        model.Add(opp * den <= num)
        model.Add(opp * den >= num - den + 1)
        opp_vars[volunteer.id] = opp

    sum_opp = sum(opp_vars.values())
    for volunteer in problem.volunteers:
        dev = model.NewIntVar(0, SCALE * 1000, f"odev_{volunteer.id}")
        model.Add(n_volunteers * dev >= n_volunteers * opp_vars[volunteer.id] - sum_opp)
        model.Add(n_volunteers * dev >= sum_opp - n_volunteers * opp_vars[volunteer.id])
        opp_deviations.append(dev)

    contribution = sum(
        task_values[c.task_id] * c.fit * x[(c.volunteer_id, c.task_id)] for c in candidates
    )
    if mode == SolverMode.FEASIBILITY:
        model.Minimize(0)
    elif mode == SolverMode.EFFICIENCY:
        model.Maximize(contribution)
    else:
        norm = policy.fairness_normalization
        lambdas = policy.lambdas
        unfairness = _int(norm * lambdas.workload_unfairness) * sum(workload_deviations)
        unfairness += _int(norm * lambdas.opportunity_unfairness) * sum(opp_deviations)
        uncertainty = _int(norm * lambdas.uncertainty_risk) * sum(
            _int(c.risk * SCALE) * x[(c.volunteer_id, c.task_id)] for c in candidates
        )
        overhead = _int(lambdas.coordination_overhead) * sum(
            len(c.unknown_fields) * x[(c.volunteer_id, c.task_id)] for c in candidates
        )
        disruption = _int(norm * lambdas.disruption) * sum(disruption_terms) if disruption_terms else 0
        model.Maximize(contribution - unfairness - uncertainty - overhead - disruption)

    # Adaptive time limit based on problem size (number of candidate variables).
    adaptive_limit = adaptive_time_limit(len(x))
    solver = configure_solver(adaptive_limit)
    raw_status = solver.Solve(model)
    runtime_ms = elapsed()

    # Fallback chain: if fairness-aware times out, try efficiency-only,
    # then feasibility-only. This ensures we always return *something*
    # useful rather than a hard timeout on large instances.
    fallback_mode = None
    if (
        mode == SolverMode.FAIRNESS_AWARE
        and raw_status not in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    ):
        fallback_mode = SolverMode.EFFICIENCY
    elif mode == SolverMode.EFFICIENCY and raw_status not in (
        cp_model.OPTIMAL,
        cp_model.FEASIBLE,
    ):
        fallback_mode = SolverMode.FEASIBILITY

    if fallback_mode is not None:
        fallback_model = cp_model.CpModel()
        fallback_x: dict[tuple[str, str], object] = {}
        for index, candidate in enumerate(
            sorted(candidates, key=lambda c: (c.task_id, c.volunteer_id))
        ):
            key = (candidate.volunteer_id, candidate.task_id)
            fallback_x[key] = fallback_model.NewBoolVar(
                f"fx_{index}_{candidate.volunteer_id}_{candidate.task_id}"
            )

        # Re-add only hard constraints (no fairness objective).
        candidates_by_task_fb: dict[str, list[Candidate]] = defaultdict(list)
        candidates_by_volunteer_fb: dict[str, list[Candidate]] = defaultdict(list)
        for candidate in candidates:
            candidates_by_task_fb[candidate.task_id].append(candidate)
            candidates_by_volunteer_fb[candidate.volunteer_id].append(candidate)

        for task in publishable_tasks:
            matching = [
                fallback_x[(c.volunteer_id, c.task_id)]
                for c in candidates_by_task_fb.get(task.id, [])
            ]
            if len(matching) < task.max_assignees:
                continue
            fallback_model.Add(sum(matching) == task.max_assignees)

        effort_by_task_fb = {t.id: _int(t.effort_hours * HOUR_SCALE) for t in problem.tasks}
        for volunteer in problem.volunteers:
            remaining = _int((volunteer.capacity_hours - volunteer.committed_hours) * HOUR_SCALE)
            terms = [
                effort_by_task_fb[c.task_id] * fallback_x[(volunteer.id, c.task_id)]
                for c in candidates_by_volunteer_fb.get(volunteer.id, [])
            ]
            fallback_model.Add(sum(terms) <= max(0, remaining))

        overlaps_fb = compute_overlap_pairs(publishable_tasks)
        for a_id, b_id in sorted(overlaps_fb):
            ids_a = {c.volunteer_id for c in candidates_by_task_fb.get(a_id, [])}
            ids_b = {c.volunteer_id for c in candidates_by_task_fb.get(b_id, [])}
            for vid in sorted(ids_a & ids_b):
                fallback_model.Add(fallback_x[(vid, a_id)] + fallback_x[(vid, b_id)] <= 1)

        completed_fb = set(problem.completed_task_ids)
        for task in publishable_tasks:
            for dep in task.dependencies:
                if dep in completed_fb:
                    continue
                dep_vars = [
                    fallback_x[(c.volunteer_id, dep)]
                    for c in candidates_by_task_fb.get(dep, [])
                ]
                for candidate in candidates_by_task_fb.get(task.id, []):
                    fallback_model.Add(
                        fallback_x[(candidate.volunteer_id, task.id)] <= sum(dep_vars)
                    )

        if fallback_mode == SolverMode.EFFICIENCY:
            contribution_fb = sum(
                task_values[c.task_id] * c.fit * fallback_x[(c.volunteer_id, c.task_id)]
                for c in candidates
            )
            fallback_model.Maximize(contribution_fb)
        # FEASIBILITY: minimize 0 (any feasible solution)

        fb_solver = configure_solver(min(adaptive_limit, MAX_TIME_LIMIT))
        fb_status = fb_solver.Solve(fallback_model)
        runtime_ms = elapsed()

        if fb_status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            selected = {
                key for key, var in fallback_x.items() if fb_solver.Value(var) == 1
            }
            proposals = sorted(
                (
                    ProposalOut(
                        volunteer_id=c.volunteer_id,
                        task_id=c.task_id,
                        fit_score=c.fit,
                        risk_score=round(c.risk, 4),
                        reasons=list(c.reasons) + [f"fallback:{fallback_mode.value}"],
                    )
                    for c in candidates
                    if (c.volunteer_id, c.task_id) in selected
                ),
                key=lambda p: (p.task_id, p.volunteer_id),
            )
            metrics = AllocationMetrics(
                assigned_tasks=len(selected),
                candidates=len(candidates),
                workload_unfairness=0,
                opportunity_unfairness=0,
                expected_contribution=expected_contribution(candidates, selected, task_values),
                uncertainty_risk=risk_term(candidates, selected),
                coordination_overhead=overhead_term(candidates, selected),
                objective_value=(
                    float(fb_solver.ObjectiveValue())
                    if fallback_mode == SolverMode.EFFICIENCY
                    else None
                ),
                optimality_gap=None,
                solver_runtime_ms=round(runtime_ms, 3),
            )
            status = (
                SolverStatus.OPTIMAL_PROPOSALS
                if fb_status == cp_model.OPTIMAL
                else SolverStatus.FEASIBLE_PROPOSALS
            )
            return AllocationResult(
                status=status,
                proposals=proposals,
                questions=questions,
                metrics=metrics,
                policy_version=policy_version,
                solver_version=solver_version,
                solver_status_raw=f"fallback:{fallback_mode.value}/{fb_solver.StatusName(fb_status)}",
            )


    if raw_status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        selected = {
            key for key, var in x.items() if solver.Value(var) == 1
        }
        proposals = sorted(
            (
                ProposalOut(
                    volunteer_id=c.volunteer_id,
                    task_id=c.task_id,
                    fit_score=c.fit,
                    risk_score=round(c.risk, 4),
                    reasons=list(c.reasons),
                )
                for c in candidates
                if (c.volunteer_id, c.task_id) in selected
            ),
            key=lambda p: (p.task_id, p.volunteer_id),
        )
        metrics = AllocationMetrics(
            assigned_tasks=len(selected),
            candidates=len(candidates),
            workload_unfairness=sum(solver.Value(v) for v in workload_deviations),
            opportunity_unfairness=sum(solver.Value(v) for v in opp_deviations),
            expected_contribution=expected_contribution(candidates, selected, task_values),
            uncertainty_risk=risk_term(candidates, selected),
            coordination_overhead=overhead_term(candidates, selected),
            objective_value=float(solver.ObjectiveValue()) if mode != SolverMode.FEASIBILITY else None,
            optimality_gap=(
                float(solver.BestObjectiveBound() - solver.ObjectiveValue()) / max(1.0, abs(solver.ObjectiveValue()))
                if raw_status == cp_model.FEASIBLE and mode != SolverMode.FEASIBILITY
                else 0.0 if raw_status == cp_model.OPTIMAL else None
            ),
            solver_runtime_ms=round(runtime_ms, 3),
        )
        status = (
            SolverStatus.OPTIMAL_PROPOSALS
            if raw_status == cp_model.OPTIMAL
            else SolverStatus.FEASIBLE_PROPOSALS
        )
        return AllocationResult(
            status=status,
            proposals=proposals,
            questions=questions,
            metrics=metrics,
            policy_version=policy_version,
            solver_version=solver_version,
            solver_status_raw=solver.StatusName(raw_status),
        )

    if raw_status == cp_model.INFEASIBLE:
        return _failure(
            problem,
            candidate_set,
            SolverStatus.NO_FEASIBLE_PROPOSAL,
            [],
            [],
            questions,
            runtime_ms,
        )

    return _failure(
        problem,
        candidate_set,
        SolverStatus.SOLVER_UNKNOWN,
        ["SOLVER_TIMEOUT"],
        ["Solver stopped without a solution; no assignment was created."],
        questions,
        runtime_ms,
    )

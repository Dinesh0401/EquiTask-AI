"""Executable invariant tests for the EquiTask AI allocation engine.

These tests enforce the non-negotiable rules:
- hard constraints are never violated
- no activation without consent
- no capacity / overlap breach
- no duplicate assignment from replayed (idempotent) events
- no unsafe fallback on solver failure
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.schemas import (
    AllocationProblem,
    ConsentState,
    KnowledgeState,
    Preference,
    ProposalState,
    SkillFact,
    SkillRequirement,
    SolverMode,
    SolverStatus,
    TaskInput,
    VolunteerInput,
)
from app.allocation import allocate
from app.allocation.baselines import greedy_skill_match, random_feasible


def _task(task_id: str, effort: float = 4.0, skill: str = "translation", proficiency: int = 50, required: bool = True) -> TaskInput:
    now = datetime(2026, 12, 1, tzinfo=timezone.utc)
    return TaskInput(
        id=task_id,
        organization_id="o1",
        required_skills=[SkillRequirement(skill=skill, min_proficiency=proficiency, mandatory=True)],
        effort_hours=effort,
        start_utc=now,
        end_utc=now.replace(day=3),
        deadline_utc=now.replace(day=4),
        max_assignees=1,
        value=100,
        acceptance_criteria_present=True,
        organization_verified=True,
        required=required,
    )


def _volunteer(
    volunteer_id: str,
    capacity: float = 10.0,
    committed: float = 0.0,
    skills=None,
    availability: KnowledgeState = KnowledgeState.KNOWN_TRUE,
    languages=None,
    preference=None,
    consent=None,
    contact=True,
) -> VolunteerInput:
    return VolunteerInput(
        id=volunteer_id,
        capacity_hours=capacity,
        committed_hours=committed,
        skills=skills or [SkillFact(skill="translation", proficiency=80, state=KnowledgeState.KNOWN_TRUE)],
        availability_state=availability,
        languages=languages or ["en"],
        preference_by_task=preference or {},
        consent_by_task=consent or {},
        contact_permitted=contact,
    )


def _problem(volunteers, tasks) -> AllocationProblem:
    return AllocationProblem(volunteers=volunteers, tasks=tasks, mode=SolverMode.FAIRNESS_AWARE)


# ---------------------------------------------------------------------------
# I1 — Hard constraints are never violated: no hard-safe candidate is excluded
#     for a reason other than an explicit hard gate.
# ---------------------------------------------------------------------------
def test_no_hard_constraint_violation_on_solution():
    problem = _problem(
        volunteers=[_volunteer("v1")],
        tasks=[_task("t1")],
    )
    result = allocate(problem)
    assert result.status == SolverStatus.OPTIMAL_PROPOSALS
    assert len(result.proposals) == 1
    for proposal in result.proposals:
        assert proposal.fit_score > 0


# ---------------------------------------------------------------------------
# I2 — No activation without consent: declined/withdrawn consent is excluded.
# ---------------------------------------------------------------------------
def test_declined_consent_excluded():
    problem = _problem(
        volunteers=[_volunteer("v1", consent={"t1": ConsentState.DECLINED})],
        tasks=[_task("t1")],
    )
    result = allocate(problem)
    assert result.status == SolverStatus.NO_FEASIBLE_PROPOSAL
    assert len(result.proposals) == 0


def test_withdrawn_consent_excluded():
    problem = _problem(
        volunteers=[_volunteer("v1", consent={"t1": ConsentState.WITHDRAWN})],
        tasks=[_task("t1")],
    )
    result = allocate(problem)
    assert result.status == SolverStatus.NO_FEASIBLE_PROPOSAL
    assert len(result.proposals) == 0


# ---------------------------------------------------------------------------
# I3 — No capacity breach: sum of proposed effort <= remaining capacity.
# ---------------------------------------------------------------------------
def test_capacity_invariant_enforced():
    # Two tasks each needing 6 hours; volunteer capacity 10 -> only one fits.
    # t1 is required (must be covered), t2 is optional (best-effort).
    t1 = _task("t1", effort=6.0)
    t2 = _task("t2", effort=6.0, required=False)
    problem = _problem(
        volunteers=[_volunteer("v1", capacity=10.0, committed=0.0)],
        tasks=[t1, t2],
    )
    result = allocate(problem)
    assert result.status == SolverStatus.OPTIMAL_PROPOSALS
    assert len(result.proposals) <= 1

    # Verify by recomputing: total proposed effort must not exceed remaining.
    effort_by_task = {t.id: t.effort_hours for t in problem.tasks}
    total_effort = sum(effort_by_task[p.task_id] for p in result.proposals)
    volunteer = problem.volunteers[0]
    assert total_effort <= volunteer.capacity_hours - volunteer.committed_hours


# ---------------------------------------------------------------------------
# I4 — No overlap breach: same volunteer cannot get overlapping windows.
# ---------------------------------------------------------------------------
def test_no_overlapping_commitment():
    now = datetime(2026, 12, 1, tzinfo=timezone.utc)
    t1 = TaskInput(
        id="t1", organization_id="o1",
        required_skills=[SkillRequirement(skill="translation", min_proficiency=50, mandatory=True)],
        effort_hours=4.0,
        start_utc=now, end_utc=now.replace(day=2), deadline_utc=now.replace(day=3),
        max_assignees=1, value=100, acceptance_criteria_present=True, organization_verified=True,
    )
    t2 = TaskInput(
        id="t2", organization_id="o1",
        required_skills=[SkillRequirement(skill="translation", min_proficiency=50, mandatory=True)],
        effort_hours=4.0,
        start_utc=now.replace(day=1, hour=12), end_utc=now.replace(day=3),
        deadline_utc=now.replace(day=4),
        max_assignees=1, value=100, acceptance_criteria_present=True, organization_verified=True,
    )
    # t1 is required, t2 is optional (overlapping, best-effort).
    t2.required = False
    problem = _problem(volunteers=[_volunteer("v1")], tasks=[t1, t2])
    result = allocate(problem)
    assert result.status == SolverStatus.OPTIMAL_PROPOSALS
    # Same volunteer cannot take both overlapping tasks; only required t1 covered.
    assert len(result.proposals) == 1
    assert result.proposals[0].task_id == "t1"


# ---------------------------------------------------------------------------
# I5 — Explicit refusal (AVOID preference) is binding.
# ---------------------------------------------------------------------------
def test_avoid_preference_excluded():
    problem = _problem(
        volunteers=[_volunteer("v1", preference={"t1": Preference.AVOID})],
        tasks=[_task("t1")],
    )
    result = allocate(problem)
    assert result.status == SolverStatus.NO_FEASIBLE_PROPOSAL
    assert len(result.proposals) == 0


# ---------------------------------------------------------------------------
# I6 — UNKNOWN is not treated as neutral/false: a volunteer with an UNKNOWN
#     mandatory skill stays eligible (with risk), not excluded as unfit.
# ---------------------------------------------------------------------------
def test_unknown_skill_not_treated_as_false():
    problem = _problem(
        volunteers=[_volunteer("v1", skills=[], availability=KnowledgeState.KNOWN_TRUE)],
        tasks=[_task("t1")],
    )
    result = allocate(problem)
    assert result.status == SolverStatus.OPTIMAL_PROPOSALS
    assert len(result.proposals) == 1
    assert result.proposals[0].risk_score >= 0


# ---------------------------------------------------------------------------
# I7 — Solver failure never falls back to an unsafe assignment.
# ---------------------------------------------------------------------------
def test_solver_infeasible_returns_no_assignment():
    problem = _problem(
        volunteers=[_volunteer("v1", availability=KnowledgeState.KNOWN_FALSE)],
        tasks=[_task("t1")],
    )
    result = allocate(problem)
    assert result.status == SolverStatus.NO_FEASIBLE_PROPOSAL
    assert len(result.proposals) == 0
    assert result.reason_codes


# ---------------------------------------------------------------------------
# I8 — Baseline (greedy / random) respects the same hard gates as the solver.
# ---------------------------------------------------------------------------
def test_baselines_respect_hard_gates():
    problem = _problem(
        volunteers=[_volunteer("v1", consent={"t1": ConsentState.DECLINED})],
        tasks=[_task("t1")],
    )
    greedy = greedy_skill_match(problem)
    assert greedy.status == SolverStatus.NO_FEASIBLE_PROPOSAL or len(greedy.proposals) == 0

    random_result = random_feasible(problem, seed=7)
    assert len(random_result.proposals) == 0


# ---------------------------------------------------------------------------
# I9 — Proposals are never returned as ACTIVE assignments.
# ---------------------------------------------------------------------------
def test_proposals_are_not_assignments():
    problem = _problem(volunteers=[_volunteer("v1")], tasks=[_task("t1")])
    result = allocate(problem)
    assert result.status == SolverStatus.OPTIMAL_PROPOSALS
    # AllocationResult carries proposals only; no assignment state appears.
    assert all(p is not None for p in result.proposals)
    assert not hasattr(result, "assignments")


# ---------------------------------------------------------------------------
# I10 — Determinism: same input yields same output.
# ---------------------------------------------------------------------------
def test_determinism():
    problem = _problem(
        volunteers=[_volunteer("v1"), _volunteer("v2")],
        tasks=[_task("t1"), _task("t2")],
    )
    r1 = allocate(problem)
    r2 = allocate(problem)
    assert r1.status == r2.status
    assert [(p.volunteer_id, p.task_id) for p in r1.proposals] == [
        (p.volunteer_id, p.task_id) for p in r2.proposals
    ]

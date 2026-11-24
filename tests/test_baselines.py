"""Tests for baselines and repair plan."""

from __future__ import annotations

from datetime import datetime, timezone

from app.schemas import (
    AllocationProblem,
    ConsentState,
    KnowledgeState,
    SolverMode,
    SolverStatus,
    SkillFact,
    SkillRequirement,
    TaskInput,
    VolunteerInput,
)
from app.allocation import allocate
from app.allocation.baselines import greedy_skill_match, random_feasible, cp_sat_efficiency, cp_sat_fairness
from app.allocation.repair import build_repair_plan


def _task(task_id: str, effort: float = 4.0, skill: str = "translation", proficiency: int = 50) -> TaskInput:
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
    )


def _volunteer(
    volunteer_id: str,
    capacity: float = 10.0,
    committed: float = 0.0,
    skills=None,
    availability: KnowledgeState = KnowledgeState.KNOWN_TRUE,
    consent=None,
) -> VolunteerInput:
    return VolunteerInput(
        id=volunteer_id,
        capacity_hours=capacity,
        committed_hours=committed,
        skills=skills or [SkillFact(skill="translation", proficiency=80, state=KnowledgeState.KNOWN_TRUE)],
        availability_state=availability,
        languages=["en"],
        preference_by_task={},
        consent_by_task=consent or {},
        contact_permitted=True,
    )


def test_greedy_covers_when_feasible():
    problem = AllocationProblem(
        volunteers=[_volunteer("v1"), _volunteer("v2")],
        tasks=[_task("t1"), _task("t2")],
    )
    result = greedy_skill_match(problem)
    assert result.status == SolverStatus.OPTIMAL_PROPOSALS
    assert len(result.proposals) == 2


def test_random_feasible_is_deterministic_given_seed():
    problem = AllocationProblem(
        volunteers=[_volunteer("v1"), _volunteer("v2")],
        tasks=[_task("t1"), _task("t2")],
    )
    r1 = random_feasible(problem, seed=7)
    r2 = random_feasible(problem, seed=7)
    assert [(p.volunteer_id, p.task_id) for p in r1.proposals] == [
        (p.volunteer_id, p.task_id) for p in r2.proposals
    ]


def test_cp_sat_efficiency_and_fairness_agree_on_feasibility():
    problem = AllocationProblem(
        volunteers=[_volunteer("v1"), _volunteer("v2")],
        tasks=[_task("t1"), _task("t2")],
    )
    re = cp_sat_efficiency(problem)
    rf = cp_sat_fairness(problem)
    assert re.status == rf.status
    assert len(re.proposals) == len(rf.proposals)


def test_repair_freezes_accepted_commitments():
    problem = AllocationProblem(
        volunteers=[_volunteer("v1"), _volunteer("v2")],
        tasks=[_task("t1"), _task("t2")],
        mode=SolverMode.REPAIR,
        locked_assignments=[
            {"volunteer_id": "v1", "task_id": "t1", "change_permitted": False, "reconfirmation_recorded": False},
            {"volunteer_id": "v2", "task_id": "t2", "change_permitted": False, "reconfirmation_recorded": False},
        ],
    )
    plan = build_repair_plan(problem, affected_volunteer_id="v1", affected_task_id="t1")
    # v1's t1 released; v2's t2 kept
    assert any(a["task_id"] == "t1" for a in plan.released)
    assert any(a["task_id"] == "t2" for a in plan.kept)
    assert "frozen" in plan.note.lower() or "unchanged" in plan.note.lower()

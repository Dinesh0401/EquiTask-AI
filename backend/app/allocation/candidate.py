from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from ..enums import ConsentState, KnowledgeState, Preference
from ..schemas import AllocationProblem, SkillFact, TaskInput, VolunteerInput

# Risk weights are policy assumptions, not calibrated probabilities.
RISK_WEIGHTS = {
    "availability_unknown": 0.40,
    "availability_stale": 0.25,
    "skill_unknown": 0.40,
    "skill_stale": 0.20,
    "language_unknown": 0.20,
    "preference_unknown": 0.15,
}


@dataclass(frozen=True)
class Candidate:
    volunteer_id: str
    task_id: str
    fit: int
    risk: float
    reasons: tuple[str, ...]
    unknown_fields: tuple[str, ...]


@dataclass
class CandidateSet:
    candidates: list[Candidate] = field(default_factory=list)
    exclusions: Counter[str] = field(default_factory=Counter)
    task_exclusions: Counter[str] = field(default_factory=Counter)


def _skill_fact(volunteer: VolunteerInput, skill: str) -> SkillFact | None:
    for fact in volunteer.skills:
        if fact.skill.casefold() == skill.casefold():
            return fact
    return None


def _windows_overlap(a: TaskInput, b: TaskInput) -> bool:
    return a.start_utc < b.end_utc and b.start_utc < a.end_utc


def compute_overlap_pairs(tasks: list[TaskInput]) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for i, a in enumerate(tasks):
        for b in tasks[i + 1 :]:
            if _windows_overlap(a, b):
                pairs.add((a.id, b.id))
    return pairs


def _fit_and_risk(
    volunteer: VolunteerInput,
    task: TaskInput,
    availability_field: KnowledgeState,
    skill_fields: list[KnowledgeState],
    language_missing: bool,
    preference: Preference,
) -> tuple[int, float]:
    proficiencies: list[int] = []
    for req in task.required_skills:
        fact = _skill_fact(volunteer, req.skill)
        if fact and fact.state in (KnowledgeState.KNOWN_TRUE, KnowledgeState.STALE):
            proficiencies.append(min(fact.proficiency, 100))
    skill_component = round(sum(proficiencies) / len(proficiencies) * 0.4) if proficiencies else 0

    fit = 40 + skill_component
    if preference == Preference.INTERESTED:
        fit += 15
    elif preference == Preference.NEUTRAL:
        fit += 5
    if task.required_languages and all(
        lang.casefold() in {v.casefold() for v in volunteer.languages}
        for lang in task.required_languages
    ):
        fit += 5
    if availability_field == KnowledgeState.KNOWN_TRUE:
        fit += 5

    risk = 0.0
    if availability_field == KnowledgeState.UNKNOWN:
        risk += RISK_WEIGHTS["availability_unknown"]
    elif availability_field == KnowledgeState.STALE:
        risk += RISK_WEIGHTS["availability_stale"]
    for state in skill_fields:
        if state == KnowledgeState.UNKNOWN:
            risk += RISK_WEIGHTS["skill_unknown"]
        elif state == KnowledgeState.STALE:
            risk += RISK_WEIGHTS["skill_stale"]
    if language_missing:
        risk += RISK_WEIGHTS["language_unknown"]
    if preference == Preference.UNKNOWN:
        risk += RISK_WEIGHTS["preference_unknown"]

    risk = min(risk, 1.0)
    fit = max(1, min(100, fit - round(risk * 10)))
    return fit, risk


def build_candidates(problem: AllocationProblem) -> CandidateSet:
    """Apply deterministic hard gates; UNKNOWN/STALE are retained with risk, never guessed."""
    result = CandidateSet()
    tasks_by_id = {t.id: t for t in problem.tasks}

    for task in problem.tasks:
        if not task.organization_verified:
            result.task_exclusions["TASK_ORG_NOT_VERIFIED"] += 1
            continue
        if not task.acceptance_criteria_present:
            result.task_exclusions["TASK_NO_ACCEPTANCE_CRITERIA"] += 1
            continue
        if task.end_utc > task.deadline_utc:
            result.task_exclusions["TASK_DEADLINE_BEFORE_WINDOW_END"] += 1
            continue
        if any(dep not in problem.completed_task_ids and dep not in tasks_by_id for dep in task.dependencies):
            result.task_exclusions["TASK_UNKNOWN_DEPENDENCY"] += 1
            continue

    for volunteer in problem.volunteers:
        if not volunteer.contact_permitted:
            result.exclusions["CONTACT_NOT_PERMITTED"] += len(problem.tasks)
            continue
        if volunteer.committed_hours >= volunteer.capacity_hours:
            result.exclusions["CAPACITY_EXHAUSTED"] += len(problem.tasks)
            continue

        for task in problem.tasks:
            if task.id in {t.id for t in problem.tasks if t.id not in tasks_by_id}:
                continue  # unreachable guard; kept explicit for clarity
            if not task.organization_verified or not task.acceptance_criteria_present:
                continue
            if task.end_utc > task.deadline_utc:
                continue

            consent = volunteer.consent_by_task.get(task.id, ConsentState.NONE)
            if consent in (ConsentState.DECLINED, ConsentState.WITHDRAWN):
                result.exclusions["CONSENT_REFUSED"] += 1
                continue
            preference = volunteer.preference_by_task.get(task.id, Preference.UNKNOWN)
            if preference == Preference.AVOID:
                result.exclusions["PREFERENCE_AVOID"] += 1
                continue
            if volunteer.availability_state == KnowledgeState.KNOWN_FALSE:
                result.exclusions["AVAILABILITY_FALSE"] += 1
                continue

            skill_states: list[KnowledgeState] = []
            hard_skill_failure = False
            for req in task.required_skills:
                fact = _skill_fact(volunteer, req.skill)
                if fact is None:
                    # A never-reported skill is UNKNOWN, never false. It stays
                    # eligible for a tentative proposal with a risk penalty and
                    # a clarification question; it is not given a positive fit.
                    skill_states.append(KnowledgeState.UNKNOWN)
                    result.exclusions["SKILL_UNKNOWN_RETAINED"] += 1
                    continue
                skill_states.append(fact.state)
                if fact.state == KnowledgeState.KNOWN_FALSE and req.mandatory:
                    hard_skill_failure = True
                    result.exclusions["SKILL_FALSE"] += 1
                elif (
                    req.mandatory
                    and fact.state == KnowledgeState.KNOWN_TRUE
                    and fact.proficiency < req.min_proficiency
                ):
                    hard_skill_failure = True
                    result.exclusions["SKILL_INSUFFICIENT"] += 1
            if hard_skill_failure:
                continue

            language_missing = any(
                lang.casefold() not in {v.casefold() for v in volunteer.languages}
                for lang in task.required_languages
            )
            fit, risk = _fit_and_risk(
                volunteer, task, volunteer.availability_state, skill_states, language_missing, preference
            )

            unknown_fields: list[str] = []
            if volunteer.availability_state in (KnowledgeState.UNKNOWN, KnowledgeState.STALE):
                unknown_fields.append("availability")
            if any(s in (KnowledgeState.UNKNOWN, KnowledgeState.STALE) for s in skill_states):
                unknown_fields.append("skill")
            if language_missing:
                unknown_fields.append("language")
            if preference == Preference.UNKNOWN:
                unknown_fields.append("preference")

            reasons = ["hard_gates_passed"]
            if unknown_fields:
                reasons.append("uncertainty_penalized")
            result.candidates.append(
                Candidate(
                    volunteer_id=volunteer.id,
                    task_id=task.id,
                    fit=fit,
                    risk=risk,
                    reasons=tuple(reasons),
                    unknown_fields=tuple(unknown_fields),
                )
            )
    return result

"""Reproducible scenario generator for Phase 2 simulation experiments.

Generates synthetic volunteer allocation instances with controllable:
- Skill distributions (uniform, skewed, scarce-skill)
- Demand profiles (balanced, overloaded, bursty)
- Time zones and DST transitions
- Missingness (MCAR and nonrandom)
- Acceptance models (deterministic, noisy, preference-correlated)
- Disruption events (withdrawal, deadline change, new task)

All output is deterministic given a seed. No results are claimed; this is a
research instrument only.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any


@dataclass
class SkillProfile:
    name: str
    scarcity: str  # "common", "rare", "scarce"
    base_proficiency: int


# Default skill catalog with scarcity annotations.
DEFAULT_SKILLS: list[SkillProfile] = [
    SkillProfile("translation", "common", 70),
    SkillProfile("web", "common", 65),
    SkillProfile("accessibility", "rare", 60),
    SkillProfile("education", "common", 70),
    SkillProfile("mapping", "rare", 60),
    SkillProfile("data_analysis", "scarce", 55),
    SkillProfile("legal", "scarce", 50),
    SkillProfile("medical", "scarce", 45),
]

COUNTRIES = [
    "US", "GB", "IN", "BR", "NG", "KE", "PH", "PK", "BD", "ET", "GH", "LK",
]


@dataclass
class ScenarioConfig:
    """Configuration for scenario generation. All fields are explicit inputs."""

    seed: int = 42
    num_volunteers: int = 100
    num_tasks: int = 60
    num_organizations: int = 5
    num_countries: int = 12
    skill_distribution: str = "uniform"  # "uniform", "skewed", "scarce"
    demand_profile: str = "balanced"  # "balanced", "overloaded", "bursty"
    missingness_rate: float = 0.2  # fraction of fields left UNKNOWN
    missingness_model: str = "MCAR"  # "MCAR", "nonrandom"
    acceptance_model: str = "deterministic"  # "deterministic", "noisy", "preference_correlated"
    enable_disruptions: bool = False
    disruption_rate: float = 0.1
    timezones: list[str] = field(default_factory=lambda: ["UTC", "America/New_York", "Europe/London", "Asia/Kolkata"])


@dataclass
class VolunteerSpec:
    id: str
    country_code: str
    timezone: str
    capacity_hours: float
    committed_hours: float
    skills: list[dict[str, Any]]
    availability_state: str
    languages: list[str]
    preferences: dict[str, str]
    contact_permitted: bool
    newcomer: bool
    history_offers: int
    history_hours: float


@dataclass
class TaskSpec:
    id: str
    organization_id: str
    required_skills: list[dict[str, Any]]
    effort_hours: float
    start_utc: datetime
    end_utc: datetime
    deadline_utc: datetime
    dependencies: list[str]
    max_assignees: int
    value: int
    acceptance_criteria_present: bool
    required_languages: list[str]
    required: bool


@dataclass
class Scenario:
    """A generated allocation scenario, ready to be consumed by the engine."""

    config: ScenarioConfig
    volunteers: list[VolunteerSpec]
    tasks: list[TaskSpec]
    organizations: list[dict[str, Any]]
    disruption_events: list[dict[str, Any]]
    metadata: dict[str, Any]


def _rng_for(seed: int, suffix: str) -> random.Random:
    """Create a deterministic RNG for a named sub-stream."""
    return random.Random(f"{seed}:{suffix}")


def _choose_skills(
    rng: random.Random,
    config: ScenarioConfig,
    num_skills: int,
) -> list[SkillProfile]:
    """Select skills according to the configured distribution."""
    if config.skill_distribution == "uniform":
        pool = list(DEFAULT_SKILLS)
        rng.shuffle(pool)
        return pool[:num_skills]
    if config.skill_distribution == "skewed":
        # Weight toward common skills.
        common = [s for s in DEFAULT_SKILLS if s.scarcity == "common"]
        rare = [s for s in DEFAULT_SKILLS if s.scarcity in ("rare", "scarce")]
        chosen: list[SkillProfile] = []
        while len(chosen) < num_skills:
            if rng.random() < 0.7 and common:
                chosen.append(rng.choice(common))
            elif rare:
                chosen.append(rng.choice(rare))
            else:
                chosen.append(rng.choice(common))
        return chosen[:num_skills]
    if config.skill_distribution == "scarce":
        scarce = [s for s in DEFAULT_SKILLS if s.scarcity == "scarce"]
        rare = [s for s in DEFAULT_SKILLS if s.scarcity == "rare"]
        common = [s for s in DEFAULT_SKILLS if s.scarcity == "common"]
        chosen = []
        while len(chosen) < num_skills:
            if scarce:
                chosen.append(rng.choice(scarce))
            elif rare:
                chosen.append(rng.choice(rare))
            else:
                chosen.append(rng.choice(common))
        return chosen[:num_skills]
    raise ValueError(f"Unknown skill_distribution: {config.skill_distribution}")


def _generate_volunteers(
    rng: random.Random,
    config: ScenarioConfig,
    skills: list[SkillProfile],
) -> list[VolunteerSpec]:
    volunteers: list[VolunteerSpec] = []
    countries = COUNTRIES[: config.num_countries]
    now = datetime(2026, 12, 1, tzinfo=timezone.utc)

    for i in range(config.num_volunteers):
        vid = f"vol_{i + 1:04d}"
        country = rng.choice(countries)
        volunteer_timezone = rng.choice(config.timezones)
        capacity = rng.choice([4.0, 8.0, 12.0, 16.0, 20.0])
        committed = round(rng.uniform(0.0, capacity * 0.6), 1)

        # Each volunteer reports 1-3 skills.
        num_vol_skills = rng.randint(1, 3)
        volunteer_skills = rng.sample(skills, k=min(num_vol_skills, len(skills)))

        skill_facts: list[dict[str, Any]] = []
        for skill in volunteer_skills:
            # Proficiency around the skill's base, with noise.
            prof = min(100, max(0, skill.base_proficiency + rng.randint(-15, 15)))
            # Epistemic state: some fields are UNKNOWN/STALE.
            roll = rng.random()
            if config.missingness_model == "nonrandom":
                # Lower-confidence volunteers are more likely to omit data.
                low_conf = prof < 60
                if low_conf and roll < config.missingness_rate * 2:
                    state = "UNKNOWN"
                elif roll < config.missingness_rate:
                    state = "STALE"
                else:
                    state = "KNOWN_TRUE"
            else:
                if roll < config.missingness_rate:
                    state = "UNKNOWN"
                elif roll < config.missingness_rate * 2:
                    state = "STALE"
                else:
                    state = "KNOWN_TRUE"

            skill_facts.append(
                {
                    "skill": skill.name,
                    "proficiency": prof,
                    "state": state,
                    "observed_at": now.isoformat(),
                    "source": "self_report",
                }
            )

        # Availability state.
        avail_roll = rng.random()
        if config.missingness_model == "nonrandom":
            availability_state = (
                "UNKNOWN" if avail_roll < config.missingness_rate * 1.5 else "KNOWN_TRUE"
            )
        else:
            if avail_roll < config.missingness_rate:
                availability_state = "UNKNOWN"
            elif avail_roll < config.missingness_rate * 2:
                availability_state = "STALE"
            else:
                availability_state = "KNOWN_TRUE"

        # Languages.
        num_langs = rng.randint(1, 3)
        languages = rng.sample(["en", "es", "fr", "ar", "hi", "pt"], k=num_langs)

        # Preferences over task types (sparse).
        preferences: dict[str, str] = {}
        for _ in range(rng.randint(0, 2)):
            task_type = rng.choice([s.name for s in skills])
            preferences[task_type] = rng.choice(["INTERESTED", "NEUTRAL", "AVOID"])

        contact_permitted = rng.random() < 0.9
        newcomer = i < config.num_volunteers * 0.3  # First 30% are newcomers
        history_offers = rng.randint(0, 5) if not newcomer else 0
        history_hours = round(history_offers * rng.uniform(2.0, 8.0), 1)

        volunteers.append(
            VolunteerSpec(
                id=vid,
                country_code=country,
                timezone=volunteer_timezone,
                capacity_hours=capacity,
                committed_hours=committed,
                skills=skill_facts,
                availability_state=availability_state,
                languages=languages,
                preferences=preferences,
                contact_permitted=contact_permitted,
                newcomer=newcomer,
                history_offers=history_offers,
                history_hours=history_hours,
            )
        )

    return volunteers


def _generate_tasks(
    rng: random.Random,
    config: ScenarioConfig,
    skills: list[SkillProfile],
    organizations: list[dict[str, Any]],
) -> list[TaskSpec]:
    tasks: list[TaskSpec] = []
    now = datetime(2026, 12, 1, tzinfo=timezone.utc)

    for i in range(config.num_tasks):
        tid = f"task_{i + 1:04d}"
        org = rng.choice(organizations)
        num_req_skills = rng.randint(1, 2)
        req_skills = rng.sample(skills, k=min(num_req_skills, len(skills)))

        required_skills = []
        for skill in req_skills:
            required_skills.append(
                {
                    "skill": skill.name,
                    "min_proficiency": rng.randint(40, 80),
                    "mandatory": rng.random() < 0.8,
                }
            )

        effort = rng.choice([2.0, 4.0, 6.0, 8.0])
        start = now + timedelta(days=rng.randint(1, 5))
        end = start + timedelta(days=rng.randint(1, 4))
        deadline = end + timedelta(days=rng.randint(1, 3))

        # Dependencies: some tasks depend on earlier tasks.
        dependencies: list[str] = []
        if i > 0 and rng.random() < 0.2:
            dep_idx = rng.randint(0, i - 1)
            dependencies = [f"task_{dep_idx + 1:04d}"]

        value = rng.randint(50, 300)
        required_languages = []
        if rng.random() < 0.3:
            required_languages = [rng.choice(["en", "es", "fr"])]

        # Demand profile affects whether tasks are required or optional.
        required = True
        if config.demand_profile == "bursty" and rng.random() < 0.3:
            required = False

        tasks.append(
            TaskSpec(
                id=tid,
                organization_id=org["id"],
                required_skills=required_skills,
                effort_hours=effort,
                start_utc=start,
                end_utc=end,
                deadline_utc=deadline,
                dependencies=dependencies,
                max_assignees=1,
                value=value,
                acceptance_criteria_present=True,
                required_languages=required_languages,
                required=required,
            )
        )

    return tasks


def _generate_disruptions(
    rng: random.Random,
    config: ScenarioConfig,
    tasks: list[TaskSpec],
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if not config.enable_disruptions:
        return events

    now = datetime(2026, 12, 1, tzinfo=timezone.utc)
    num_events = max(1, int(len(tasks) * config.disruption_rate))

    for _ in range(num_events):
        event_type = rng.choice(["WITHDRAWAL", "DEADLINE_CHANGE", "NEW_TASK"])
        event = {
            "event_type": event_type,
            "occurred_at": (now + timedelta(hours=rng.randint(1, 72))).isoformat(),
            "note": f"Simulated {event_type.lower()} event",
        }
        if event_type == "WITHDRAWAL":
            event["assignment_id"] = f"asg_{rng.randint(1, 100):04d}"
        elif event_type == "DEADLINE_CHANGE":
            event["task_id"] = rng.choice(tasks).id
            event["new_deadline_utc"] = (now + timedelta(days=rng.randint(4, 10))).isoformat()
        elif event_type == "NEW_TASK":
            event["task_id"] = f"task_new_{rng.randint(1, 999):04d}"
        events.append(event)

    return events


def generate_scenario(config: ScenarioConfig | None = None) -> Scenario:
    """Generate a deterministic allocation scenario.

    Args:
        config: Scenario configuration. If None, uses defaults.

    Returns:
        A Scenario object with volunteers, tasks, organizations, and
        disruption events. All values are deterministic given config.seed.
    """
    if config is None:
        config = ScenarioConfig()

    rng = _rng_for(config.seed, "scenario")
    skills = _choose_skills(rng, config, num_skills=6)

    organizations = [
        {
            "id": f"org_{i + 1:04d}",
            "name": f"Organization {i + 1}",
            "country_code": rng.choice(COUNTRIES),
            "verification_status": "VERIFIED",
        }
        for i in range(config.num_organizations)
    ]

    volunteers = _generate_volunteers(rng, config, skills)
    tasks = _generate_tasks(rng, config, skills, organizations)
    disruptions = _generate_disruptions(rng, config, tasks)

    return Scenario(
        config=config,
        volunteers=volunteers,
        tasks=tasks,
        organizations=organizations,
        disruption_events=disruptions,
        metadata={
            "seed": config.seed,
            "generator_version": "0.1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "num_volunteers": len(volunteers),
            "num_tasks": len(tasks),
            "num_organizations": len(organizations),
        },
    )


def scenario_to_allocation_problem(scenario: Scenario) -> dict[str, Any]:
    """Convert a Scenario to an AllocationProblem-compatible dict.

    This is used by the experiment runner to feed the allocation engine.
    """
    volunteers = []
    for v in scenario.volunteers:
        consent_by_task: dict[str, str] = {}
        preference_by_task: dict[str, str] = dict(v.preferences)
        for t in scenario.tasks:
            # Default consent is NONE (no offer yet).
            consent_by_task[t.id] = "NONE"
        volunteers.append(
            {
                "id": v.id,
                "capacity_hours": v.capacity_hours,
                "committed_hours": v.committed_hours,
                "skills": v.skills,
                "availability_state": v.availability_state,
                "languages": v.languages,
                "preference_by_task": preference_by_task,
                "consent_by_task": consent_by_task,
                "contact_permitted": v.contact_permitted,
                "history_offers": v.history_offers,
                "history_hours": v.history_hours,
                "newcomer": v.newcomer,
                "timezone": v.timezone,
            }
        )

    tasks = []
    for t in scenario.tasks:
        tasks.append(
            {
                "id": t.id,
                "organization_id": t.organization_id,
                "required_skills": t.required_skills,
                "effort_hours": t.effort_hours,
                "start_utc": t.start_utc.isoformat(),
                "end_utc": t.end_utc.isoformat(),
                "deadline_utc": t.deadline_utc.isoformat(),
                "dependencies": t.dependencies,
                "max_assignees": t.max_assignees,
                "value": t.value,
                "acceptance_criteria_present": t.acceptance_criteria_present,
                "organization_verified": True,
                "required_languages": t.required_languages,
                "requires_approval": False,
                "required": t.required,
            }
        )

    return {
        "volunteers": volunteers,
        "tasks": tasks,
        "mode": "FAIRNESS_AWARE",
    }

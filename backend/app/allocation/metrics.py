from __future__ import annotations

from .candidate import Candidate


def risk_term(candidates: list[Candidate], selected: set[tuple[str, str]]) -> int:
    return int(sum(1000 * c.risk for c in candidates if (c.volunteer_id, c.task_id) in selected))


def overhead_term(candidates: list[Candidate], selected: set[tuple[str, str]]) -> int:
    return sum(len(c.unknown_fields) for c in candidates if (c.volunteer_id, c.task_id) in selected)


def expected_contribution(candidates: list[Candidate], selected: set[tuple[str, str]], values: dict[str, int]) -> int:
    return sum(values.get(c.task_id, 0) * c.fit for c in candidates if (c.volunteer_id, c.task_id) in selected)

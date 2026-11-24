from __future__ import annotations

from ..schemas import AllocationResult


def explain_result(result: AllocationResult) -> list[str]:
    """Build explanations only from solver output and permitted evidence.

    Never mentions another volunteer's private attributes and never claims a
    fairness guarantee that was not verified.
    """
    explanations: list[str] = []
    if result.status in ("NO_FEASIBLE_PROPOSAL", "SOLVER_UNKNOWN"):
        for code, message in zip(result.reason_codes, result.messages):
            explanations.append(f"{code}: {message}")
        if not explanations:
            explanations.append("No feasible proposal was found under the stated hard constraints.")
        return explanations

    for proposal in result.proposals:
        parts = [
            f"Task {proposal.task_id} was proposed to volunteer {proposal.volunteer_id}.",
            f"Fit score {proposal.fit_score}/100 from declared skills, language and stated preference.",
        ]
        if proposal.risk_score > 0:
            parts.append(
                f"Uncertainty score {proposal.risk_score:.2f}; a clarification may be requested. "
                "No missing value was guessed and no assignment is active."
            )
        else:
            parts.append("All decisive fields were known at solve time; no assignment is active until consent is recorded.")
        explanations.append(" ".join(parts))
    return explanations

from __future__ import annotations

from ..enums import AssignmentState, ConsentState, ProposalState

PROPOSAL_TRANSITIONS: dict[ProposalState, set[ProposalState]] = {
    ProposalState.DRAFT: {ProposalState.VALIDATED},
    ProposalState.VALIDATED: {ProposalState.OFFERED},
    ProposalState.OFFERED: {
        ProposalState.ACCEPTED,
        ProposalState.DECLINED,
        ProposalState.EXPIRED,
    },
    ProposalState.ACCEPTED: {ProposalState.PENDING_APPROVAL, ProposalState.EXPIRED},
    ProposalState.PENDING_APPROVAL: {ProposalState.DECLINED, ProposalState.EXPIRED},
    ProposalState.DECLINED: set(),
    ProposalState.EXPIRED: set(),
}

ASSIGNMENT_TRANSITIONS: dict[AssignmentState, set[AssignmentState]] = {
    AssignmentState.PENDING_APPROVAL: {AssignmentState.ACTIVE, AssignmentState.WITHDRAWN},
    AssignmentState.ACTIVE: {
        AssignmentState.SUBMITTED,
        AssignmentState.DISPUTED,
        AssignmentState.WITHDRAWN,
    },
    AssignmentState.SUBMITTED: {AssignmentState.UNDER_REVIEW, AssignmentState.WITHDRAWN},
    AssignmentState.UNDER_REVIEW: {AssignmentState.COMPLETED, AssignmentState.DISPUTED},
    AssignmentState.DISPUTED: {AssignmentState.UNDER_REVIEW, AssignmentState.WITHDRAWN},
    AssignmentState.COMPLETED: set(),
    AssignmentState.WITHDRAWN: set(),
}


class InvalidTransition(ValueError):
    pass


def transition_proposal(current: ProposalState, target: ProposalState) -> ProposalState:
    if target not in PROPOSAL_TRANSITIONS.get(current, set()):
        raise InvalidTransition(f"proposal transition {current.value} -> {target.value} is not allowed")
    return target


def transition_assignment(current: AssignmentState, target: AssignmentState) -> AssignmentState:
    if target not in ASSIGNMENT_TRANSITIONS.get(current, set()):
        raise InvalidTransition(f"assignment transition {current.value} -> {target.value} is not allowed")
    return target


def consent_to_proposal_state(consent: ConsentState) -> ProposalState:
    mapping = {
        ConsentState.ACCEPTED: ProposalState.ACCEPTED,
        ConsentState.DECLINED: ProposalState.DECLINED,
        ConsentState.WITHDRAWN: ProposalState.EXPIRED,
        ConsentState.OFFERED: ProposalState.OFFERED,
        ConsentState.NONE: ProposalState.OFFERED,
    }
    return mapping[consent]

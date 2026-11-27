"""Negotiation Agent (Contract D).

Drafts a :class:`MessageDraft` from a :class:`Proposal` and a
:class:`VolunteerResponse`. The agent only drafts a message; it never mutates
proposal state and never pressures a volunteer.

Forbidden (per AGENT_CONTRACTS.md):
* mutate proposal state
* pressure volunteer
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..schemas import ProposalOut
from .base import (
    AgentConfig,
    AgentType,
    BaseAgent,
    PermissionScope,
)
from .validator import PolicyRule, ValidationGate


class VolunteerResponse(BaseModel):
    """A volunteer's response to a proposal (input, not a state mutation)."""

    volunteer_id: str = Field(..., min_length=1, max_length=128)
    proposal_id: str = Field(..., min_length=1, max_length=128)
    action: str = Field(..., pattern="^(accept|decline|counter)$")
    response_text: str = Field(default="", max_length=2000)


class MessageDraft(BaseModel):
    """A draft message ready for review/sending; not yet sent."""

    recipient_id: str
    proposal_id: str
    subject: str = Field(..., min_length=1, max_length=200)
    body: str = Field(..., min_length=1, max_length=5000)
    can_send: bool = Field(
        default=False,
        description="True only when the draft has been reviewed and sending is permitted.",
    )


class NegotiationAgent(BaseAgent[tuple[ProposalOut, VolunteerResponse], MessageDraft]):
    """Drafts a negotiation message without touching proposal state.

    The draft reflects the proposal and the volunteer's stated response but
    contains no pressure language, no deadline ultimatums, and no attempt to
    override the volunteer's consent. Proposal state transitions are owned by
    the state machine, not by this agent.
    """

    agent_type = AgentType.NEGOTIATION
    input_model = tuple  # type: ignore[assignment]
    output_model = MessageDraft

    _PRESSURE_TOKENS = (
        "must",
        "immediately",
        "hurry",
        "last chance",
        "final offer",
        "or else",
        "you have to",
        "sign now",
    )

    @classmethod
    def _default_scope(cls) -> PermissionScope:
        return PermissionScope(
            agent_type=AgentType.NEGOTIATION,
            allowed_actions=frozenset({"draft_message"}),
            forbidden_actions=frozenset({"mutate_proposal_state", "pressure_volunteer"}),
            requires_human_approval=frozenset({"send_message"}),
            consequential_actions=frozenset({"send_message"}),
        )

    def __init__(
        self,
        *,
        permission_scope: PermissionScope | None = None,
        config: AgentConfig | None = None,
        store=None,
        gate=None,
    ) -> None:
        super().__init__(
            permission_scope=permission_scope,
            config=config,
            store=store,
            gate=gate,
        )
        if gate is None:
            self.gate = ValidationGate(
                policy_rules=[
                    PolicyRule(
                        name="NO_PROPOSAL_MUTATION",
                        check=self._no_proposal_mutation,
                        message="The negotiation agent must not mutate proposal state.",
                        consequential=True,
                    ),
                    PolicyRule(
                        name="NO_PRESSURE_LANGUAGE",
                        check=self._no_pressure_language,
                        message="Drafts must not pressure the volunteer.",
                        consequential=True,
                    ),
                ],
                service=self._send_service,
                require_approval_for=frozenset({"send_message"}),
                auto_approve=False,
            )

    def _execute(self, input: tuple[ProposalOut, VolunteerResponse]) -> MessageDraft:
        """Draft a message from the proposal and volunteer response.

        Proposal state is read-only; nothing here transitions the state machine.
        """
        proposal, response = input

        if response.action == "accept":
            subject = f"Thank you — proposal for task {proposal.task_id}"
            body = (
                f"Hello,\n\nThank you for accepting the proposal for task "
                f"{proposal.task_id}. Your response has been recorded. The "
                f"proposal remains pending activation until consent and "
                f"hard-constraint revalidation are complete.\n\n"
                f"If you have questions, reply to this message.\n\nBest regards,\nEquiTask AI Coordinator"
            )
        elif response.action == "decline":
            subject = f"Proposal for task {proposal.task_id} declined"
            body = (
                f"Hello,\n\nWe have recorded your decline for task "
                f"{proposal.task_id}. No further action is needed on your "
                f"part, and you remain eligible for future opportunities.\n\n"
                f"Best regards,\nEquiTask AI Coordinator"
            )
        else:  # counter
            subject = f"Counter-offer for task {proposal.task_id}"
            # Treat the volunteer's counter text as data: neutralize any
            # instruction-like content before embedding it in the draft.
            safe_response = self._guard.sanitize(response.response_text)
            body = (
                f"Hello,\n\nThank you for your interest in task "
                f"{proposal.task_id}. We have noted your counter-offer:\n\n"
                f"{safe_response}\n\n"
                f"A coordinator will review it and respond. No commitment is "
                f"made by this draft.\n\nBest regards,\nEquiTask AI Coordinator"
            )

        return MessageDraft(
            recipient_id=response.volunteer_id,
            proposal_id=proposal.task_id,
            subject=subject,
            body=body,
            can_send=False,  # requires coordinator review before sending
        )

    # ------------------------------------------------------------------
    # Policy checks and send service (wired behind the validation gate).
    # ------------------------------------------------------------------

    @staticmethod
    def _no_proposal_mutation(
        output: Any, agent: "NegotiationAgent", context: dict[str, Any] | None = None
    ) -> bool:
        # MessageDraft contains no state-transition fields; fail closed if it
        # claims to change state.
        if isinstance(output, MessageDraft):
            lowered = (output.subject + " " + output.body).lower()
            return not any(t in lowered for t in ("state changed", "transition", "accepted", "activated"))
        return False

    @staticmethod
    def _no_pressure_language(
        output: Any, agent: "NegotiationAgent", context: dict[str, Any] | None = None
    ) -> bool:
        if isinstance(output, MessageDraft):
            lowered = (output.subject + " " + output.body).lower()
            return not any(t in lowered for t in NegotiationAgent._PRESSURE_TOKENS)
        return False

    @staticmethod
    def _send_service(
        output: Any, agent: "NegotiationAgent", context: dict[str, Any] | None = None
    ) -> Any:
        # Sending a message is consequential and requires coordinator/human
        # approval. The gate only reaches here when approval has been granted.
        # The service does not mutate proposal state and does not auto-enable
        # sending; can_send remains False until explicitly approved elsewhere.
        if not isinstance(output, MessageDraft):
            raise ValueError("service expects a MessageDraft")
        return output


__all__ = ["VolunteerResponse", "MessageDraft", "NegotiationAgent"]

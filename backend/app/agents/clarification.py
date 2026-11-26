"""Clarification Agent (Contract B).

Turns an :class:`EpistemicAudit` into a :class:`QuestionList`: one question
per unknown or stale field, each with field, reason, burden, and expected
value. The agent never invents or assumes an answer and never contacts a
volunteer without permission.

Forbidden (per AGENT_CONTRACTS.md):
* invent / assume an answer
* contact without permission
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

from ..schemas import ClarificationQuestion
from .base import (
    AgentConfig,
    AgentType,
    BaseAgent,
    PermissionScope,
)


class EpistemicAudit(BaseModel):
    """Audit of what is known, unknown, or stale for a volunteer/task pair.

    Used to derive clarification questions rather than guess missing values.
    """

    volunteer_id: str = Field(..., min_length=1, max_length=128)
    task_id: str | None = Field(default=None, max_length=128)
    unknown_fields: list[str] = Field(default_factory=list)
    stale_fields: list[str] = Field(default_factory=list)
    contact_permitted: bool = Field(
        default=False,
        description="Whether the volunteer has granted contact permission.",
    )
    context: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_fields(self) -> "EpistemicAudit":
        all_fields = set(self.unknown_fields) | set(self.stale_fields)
        if not all_fields:
            raise ValueError("at least one unknown or stale field is required")
        return self


class QuestionList(BaseModel):
    """List of clarification questions to ask a volunteer."""

    volunteer_id: str
    task_id: str | None = None
    questions: list[ClarificationQuestion] = Field(default_factory=list)
    total_burden: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _compute_burden(self) -> "QuestionList":
        self.total_burden = sum(q.burden for q in self.questions)
        return self


class ClarificationAgent(BaseAgent[EpistemicAudit, QuestionList]):
    """Derives clarification questions from an epistemic audit.

    For each unknown or stale field the agent emits one question with a
    reason, burden (1-5), and expected value. It never fills in an answer
    itself and only proposes questions when contact is permitted.
    """

    agent_type = AgentType.CLARIFICATION
    input_model = EpistemicAudit
    output_model = QuestionList

    # Burden per field kind: availability and skill require more volunteer effort.
    _BURDEN_BY_FIELD = {
        "availability": 3,
        "skill": 3,
        "skill.": 3,
        "language": 2,
        "preference": 2,
        "consent": 1,
    }

    @classmethod
    def _default_scope(cls) -> PermissionScope:
        return PermissionScope(
            agent_type=AgentType.CLARIFICATION,
            allowed_actions=frozenset({"send_question"}),
            forbidden_actions=frozenset({"invent_answer", "assume_answer", "contact_without_permission"}),
            requires_human_approval=frozenset({"contact_without_permission"}),
            consequential_actions=frozenset({"contact_without_permission"}),
        )

    def _execute(self, input: EpistemicAudit) -> QuestionList:
        """Pure derivation of questions from the audit.

        No answer is invented or assumed. Questions are only emitted for
        fields that are genuinely unknown or stale. If contact is not
        permitted, no questions are produced (contact without permission is
        forbidden).
        """
        questions: list[ClarificationQuestion] = []

        if not input.contact_permitted:
            # Contact without permission is forbidden; return an empty list
            # rather than attempting to contact the volunteer.
            return QuestionList(
                volunteer_id=input.volunteer_id,
                task_id=input.task_id,
                questions=[],
            )

        fields = list(dict.fromkeys(input.unknown_fields + input.stale_fields))
        for field in fields:
            task_id = input.task_id or input.context.get("task_id")
            reason = self._reason_for(field)
            burden = self._burden_for(field)
            expected_value = self._expected_value(field, input.context)
            questions.append(
                ClarificationQuestion(
                    volunteer_id=input.volunteer_id,
                    field=field,
                    task_id=task_id,
                    reason=reason,
                    burden=burden,
                    expected_value=expected_value,
                )
            )

        questions.sort(key=lambda q: (-q.expected_value, q.burden, q.field))
        return QuestionList(
            volunteer_id=input.volunteer_id,
            task_id=input.task_id,
            questions=questions,
        )

    # ------------------------------------------------------------------
    # Pure scoring helpers (deterministic; no guessing).
    # ------------------------------------------------------------------

    @staticmethod
    def _reason_for(field: str) -> str:
        return f"{field} is UNKNOWN or STALE and affects allocation feasibility or fit."

    @classmethod
    def _burden_for(cls, field: str) -> int:
        for prefix, burden in cls._BURDEN_BY_FIELD.items():
            if field == prefix or field.startswith(prefix):
                return burden
        return 2

    @staticmethod
    def _expected_value(field: str, context: dict[str, Any]) -> float:
        base = float(context.get(field, 0.0)) if context else 0.0
        return round(max(0.0, base), 4)


__all__ = ["EpistemicAudit", "QuestionList", "ClarificationAgent"]

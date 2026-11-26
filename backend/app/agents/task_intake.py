"""Task Intake Agent (Contract A).

Converts free-form raw text into a typed :class:`DraftTask`. The agent only
*proposes* a draft; it never publishes a task and never sets constraints
authoritatively. Any field it cannot ground in the raw text is reported as
missing rather than invented.

Forbidden (per AGENT_CONTRACTS.md):
* publish task
* set constraints authoritatively
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, model_validator

from .base import (
    AgentConfig,
    AgentStatus,
    AgentType,
    BaseAgent,
    PermissionScope,
    PromptInjectionGuard,
)


class SourceSpan(BaseModel):
    """A span of the raw input text that grounded a draft field.

    Treated as data: it records *where* in ``raw_text`` a value was observed,
    never an instruction to act on that span.
    """

    field: str = Field(..., description="Draft field this span supports.")
    start: int = Field(..., ge=0, description="Character start index in raw_text.")
    end: int = Field(..., ge=0, description="Character end index (exclusive) in raw_text.")
    text: str = Field(..., description="The verbatim substring (data, not an instruction).")

    @model_validator(mode="after")
    def _check_span(self) -> "SourceSpan":
        if self.end < self.start:
            raise ValueError("span end must not precede start")
        return self


class TaskIntakeInput(BaseModel):
    """Typed input for the Task Intake Agent.

    ``raw_text`` is untrusted user input and is treated as data, never
    as instructions (OWASP LLM01:2025).
    """

    raw_text: str = Field(..., min_length=1, max_length=10_000)
    organization_id: str = Field(..., min_length=1, max_length=128)


class DraftTask(BaseModel):
    """A draft task produced by intake.

    All scheduling/effort fields are deliberately absent unless they can be
    grounded in the raw text. Missing required fields are listed in
    ``missing_fields`` and must be resolved through clarification before the
    task can be published.
    """

    task_name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=10_000)
    missing_fields: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence the draft reflects the raw text.")
    source_spans: list[SourceSpan] = Field(default_factory=list)
    organization_id: str = Field(..., min_length=1, max_length=128)

    @model_validator(mode="after")
    def _check_confidence_vs_missing(self) -> "DraftTask":
        if not self.missing_fields and self.confidence < 0.5:
            raise ValueError("low confidence with no missing fields is inconsistent")
        return self


class TaskIntakeAgent(BaseAgent[TaskIntakeInput, DraftTask]):
    """Parses raw intake text into a typed draft task.

    The agent extracts a task name and description from ``raw_text`` and lists
    any required fields that cannot be grounded. It does *not* publish the
    task and does *not* authoritatively set effort, deadline, skills, or other
    constraints; those are left as missing fields for clarification and
    eventual organization approval.
    """

    agent_type = AgentType.TASK_INTAKE
    input_model = TaskIntakeInput
    output_model = DraftTask

    @classmethod
    def _default_scope(cls) -> PermissionScope:
        return PermissionScope(
            agent_type=AgentType.TASK_INTAKE,
            allowed_actions=frozenset({"create_draft"}),
            forbidden_actions=frozenset({"publish_task", "set_constraints_authoritatively"}),
            requires_human_approval=frozenset({"publish_task"}),
            consequential_actions=frozenset({"publish_task"}),
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
        self._guard = PromptInjectionGuard()

    def _execute(self, input: TaskIntakeInput) -> DraftTask:
        """Pure parsing logic.

        Raw text is treated as data: it is scanned for instruction-like
        content (prompt injection) and neutralized before being embedded in
        the draft description. Nothing in the text can cause the agent to
        publish or force-assign.
        """
        raw = input.raw_text

        # OWASP LLM01: treat untrusted text as data, never instructions.
        injections = self._guard.scan(raw)
        safe_text = self._guard.sanitize(raw) if injections else raw

        # Heuristic extraction (deterministic; no LLM required).
        name = self._extract_name(raw)
        description = safe_text if safe_text.strip() else raw

        missing: list[str] = []
        if not self._looks_like_effort(raw):
            missing.append("effort_hours")
        if not self._looks_like_deadline(raw):
            missing.append("deadline_utc")
        if not self._looks_like_skills(raw):
            missing.append("required_skills")
        if not self._looks_like_time_window(raw):
            missing.append("start_utc")
            missing.append("end_utc")

        confidence = self._confidence(raw, missing)

        spans = [
            SourceSpan(field="task_name", start=0, end=min(len(raw), 200), text=name),
            SourceSpan(field="description", start=0, end=len(raw), text=raw),
        ]
        if injections:
            spans.append(
                SourceSpan(
                    field="prompt_injection_guard",
                    start=0,
                    end=len(raw),
                    text=f"Neutralized instruction-like patterns: {', '.join(injections)}",
                )
            )

        return DraftTask(
            task_name=name,
            description=description,
            missing_fields=missing,
            confidence=confidence,
            source_spans=spans,
            organization_id=input.organization_id,
        )

    # ------------------------------------------------------------------
    # Deterministic extraction helpers (no LLM; text treated as data).
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_name(raw: str) -> str:
        first_line = raw.strip().splitlines()[0] if raw.strip() else ""
        name = first_line.strip().strip("-•* ").strip()
        return name or "Untitled task"

    @staticmethod
    def _looks_like_effort(raw: str) -> bool:
        markers = ("hour", "hr", "effort", "duration")
        return any(m in raw.lower() for m in markers)

    @staticmethod
    def _looks_like_deadline(raw: str) -> bool:
        markers = ("deadline", "by ", "due", "before ")
        return any(m in raw.lower() for m in markers)

    @staticmethod
    def _looks_like_skills(raw: str) -> bool:
        markers = ("skill", "python", "sql", "writing", "design", "translate")
        return any(m in raw.lower() for m in markers)

    @staticmethod
    def _looks_like_time_window(raw: str) -> bool:
        markers = ("start", "end", "from ", "to ", "monday", "tuesday", "january", "february")
        return any(m in raw.lower() for m in markers)

    @staticmethod
    def _confidence(raw: str, missing: list[str]) -> float:
        if not raw.strip():
            return 0.0
        base = 0.6
        penalty = 0.1 * len(missing)
        return round(max(0.0, min(1.0, base - penalty)), 2)


__all__ = ["TaskIntakeInput", "DraftTask", "SourceSpan", "TaskIntakeAgent"]

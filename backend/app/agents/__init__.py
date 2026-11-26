"""EquiTask AI agent adapters (Phase 3: genuine multi-agent coordination).

All agents are optional, typed adapters. None of them requires an LLM; each
wraps deterministic logic behind a hard-constraint validation gate
(schema -> policy -> human approval if consequential -> service call).

Agents:
    TaskIntakeAgent          - raw_text -> DraftTask (draft only; never publish)
    ClarificationAgent       - EpistemicAudit -> QuestionList (never invent answers)
    AllocationPlanningAgent  - AllocationProblem -> SolverRequest (never assigns)
    NegotiationAgent         - Proposal + VolunteerResponse -> MessageDraft (never mutates state)
    RecoveryAgent            - DisruptionEvent + state -> RepairDiff (never silently modifies)
    AuditExplanationAgent    - AllocationResult + evidence -> Explanation (no private data / guarantees)

Common guarantees (per docs/AGENT_CONTRACTS.md):
    * Typed Pydantic input and output.
    * Explicit permission scope.
    * Timeout and compute/token budget.
    * Idempotency key for side effects.
    * Retries with backoff; no side effects on invalid output.
    * Trace ID and policy version recorded on every AgentRun.
    * Untrusted text treated as data, never instructions (OWASP LLM01:2025).
    * Invalid output writes AgentRun(status=INVALID_OUTPUT) and never reaches
      the state machine.

No novelty is claimed; this is a deterministic, auditable coordination layer.
"""

from __future__ import annotations

from .allocation_planning import AllocationPlanningAgent, SolverRequest
from .audit_explanation import (
    AuditExplanationAgent,
    AuditExplanationInput,
    Explanation,
    ExplanationSegment,
)
from .base import (
    AgentConfig,
    AgentRunError,
    AgentRunRecord,
    AgentRunResult,
    AgentStatus,
    BaseAgent,
    InvalidOutputError,
    PermissionScope,
    PendingApprovalError,
    PromptInjectionGuard,
)
from .clarification import ClarificationAgent, EpistemicAudit, QuestionList
from .negotiation import MessageDraft, NegotiationAgent, VolunteerResponse
from .registry import AgentRegistry
from .recovery import DisruptionEvent, RecoveryAgent, RecoveryInput, RepairDiff
from .task_intake import DraftTask, SourceSpan, TaskIntakeAgent, TaskIntakeInput
from .validator import (
    GateResult,
    PolicyRule,
    ValidationGate,
    no_force_assign_rule,
    no_private_volunteer_data_rule,
    no_publish_without_approval_rule,
    no_unverified_guarantee_rule,
)

__all__ = [
    # Base framework
    "BaseAgent",
    "AgentConfig",
    "AgentStatus",
    "AgentRunRecord",
    "AgentRunResult",
    "PermissionScope",
    "PromptInjectionGuard",
    "AgentRunError",
    "InvalidOutputError",
    "PendingApprovalError",
    # Registry / gate
    "AgentRegistry",
    "ValidationGate",
    "PolicyRule",
    "GateResult",
    "no_force_assign_rule",
    "no_private_volunteer_data_rule",
    "no_publish_without_approval_rule",
    "no_unverified_guarantee_rule",
    # Agents
    "TaskIntakeAgent",
    "TaskIntakeInput",
    "DraftTask",
    "SourceSpan",
    "ClarificationAgent",
    "EpistemicAudit",
    "QuestionList",
    "AllocationPlanningAgent",
    "SolverRequest",
    "NegotiationAgent",
    "VolunteerResponse",
    "MessageDraft",
    "RecoveryAgent",
    "DisruptionEvent",
    "RecoveryInput",
    "RepairDiff",
    "AuditExplanationAgent",
    "AuditExplanationInput",
    "Explanation",
    "ExplanationSegment",
]

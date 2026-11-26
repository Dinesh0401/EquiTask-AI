"""Base agent framework for EquiTask AI agent adapters.

All agents are optional, typed adapters. They never call the allocation state
machine directly; they produce typed outputs that a validation gate routes
through schema validation, policy validation, and (optionally) human approval
before any side effect occurs.

Design decisions (no novelty claimed; mirrors AGENT_CONTRACTS.md):

* Deterministic by default. No LLM is required for the allocation engine.
  An agent wraps a pure ``_execute`` callable. If an LLM is later added, it
  must be wrapped by the same hard-constraint validator (see the
  "LLM-only baseline" note in AGENT_CONTRACTS.md).
* Untrusted text is treated as data, never instructions (OWASP LLM01:2025
  prompt injection). The :class:`PromptInjectionGuard` scans and neutralizes
  instruction-like content in raw input.
* Invalid output writes an ``AgentRun`` with status ``INVALID_OUTPUT`` and
  raises; it never reaches the state machine and causes no side effect.
* Retries use exponential backoff. Side effects occur only after output passes
  schema validation, policy validation, and (when consequential) human approval.
* Every run records a trace ID and policy version.
"""

from __future__ import annotations

import json
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from ..enums import AgentType

InputT = TypeVar("InputT", bound=BaseModel)
OutputT = TypeVar("OutputT", bound=BaseModel)


class AgentStatus(str, Enum):
    """Terminal statuses recorded on every AgentRun."""

    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    INVALID_OUTPUT = "INVALID_OUTPUT"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    PENDING_APPROVAL = "PENDING_APPROVAL"


class AgentRunError(RuntimeError):
    """Raised when an agent run cannot complete."""


class InvalidOutputError(AgentRunError):
    """Raised when agent output fails schema or policy validation."""


class PendingApprovalError(AgentRunError):
    """Raised when a consequential action awaits human approval."""


@dataclass(frozen=True)
class PermissionScope:
    """Declares what an agent is permitted to do.

    Attributes:
        agent_type: The :class:`AgentType` this scope belongs to.
        allowed_actions: Actions the agent may take.
        forbidden_actions: Actions the agent MUST NOT take; enforced by policy.
        requires_human_approval: Actions that need a human in the loop.
        consequential_actions: Actions that cause state change / side effects.
    """

    agent_type: AgentType
    allowed_actions: frozenset[str] = field(default_factory=frozenset)
    forbidden_actions: frozenset[str] = field(default_factory=frozenset)
    requires_human_approval: frozenset[str] = field(default_factory=frozenset)
    consequential_actions: frozenset[str] = field(default_factory=frozenset)

    def permits(self, action: str) -> bool:
        """True if ``action`` is allowed and not forbidden."""
        return action in self.allowed_actions and action not in self.forbidden_actions

    def forbids(self, action: str) -> bool:
        return action in self.forbidden_actions

    def is_consequential(self, action: str) -> bool:
        return action in self.consequential_actions


@dataclass(frozen=True)
class AgentConfig:
    """Runtime budget and policy for an agent.

    Attributes:
        timeout_seconds: Wall-clock budget for a single ``_execute`` call.
        max_tokens: Token / compute budget (advisory; enforced by callers).
        max_retries: Number of retries after a failure before giving up.
        backoff_base_seconds: Base for exponential backoff between retries.
        policy_version: Policy version recorded on every AgentRun.
        treat_untrusted_as_data: If True, raw text is never executed as instructions.
    """

    timeout_seconds: float = 30.0
    max_tokens: int | None = None
    max_retries: int = 3
    backoff_base_seconds: float = 0.5
    policy_version: str = "v0.1.1"
    treat_untrusted_as_data: bool = True


class AgentRunRecord(BaseModel):
    """Persisted (or in-memory) record of a single agent run.

    Mirrors the ``agent_runs`` table columns so agents can operate without a
    SQLAlchemy session. The record can be handed to the persistence layer.
    ``output_json`` stores the serialized typed output for idempotent replay.
    """

    run_id: str
    agent_type: AgentType
    status: AgentStatus
    input_ref: str | None = None
    output_ref: str | None = None
    output_json: str | None = None
    tokens: int = 0
    cost_usd: float = 0.0
    policy_version: str = "v0.1.1"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    error: str | None = None
    trace_id: str | None = None


@dataclass(frozen=True)
class AgentRunResult(Generic[OutputT]):
    """Outcome of :meth:`BaseAgent.run`."""

    output: OutputT
    run: AgentRunRecord
    status: AgentStatus


class PromptInjectionGuard:
    """Detects and neutralizes instruction-like content in untrusted text.

    Implements the OWASP LLM01:2025 prompt-injection defense: untrusted text is
    treated as data, never as instructions. The guard scans raw input for
    instruction-like patterns and provides a sanitized, data-safe rendering.
    Agents must pass raw user text through the guard before using it as data
    and must never concatenate it into a system prompt.
    """

    INJECTION_PATTERNS = (
        "ignore previous instructions",
        "ignore all previous",
        "disregard",
        "system:",
        "developer:",
        "override",
        "jailbreak",
        "force_assign",
        "assign everything to",
        "bypass",
        "without approval",
        "reveal",
        "another volunteer",
    )

    def scan(self, text: str) -> list[str]:
        """Return detected instruction-like patterns (case-insensitive substring match)."""
        lowered = text.lower()
        return [p for p in self.INJECTION_PATTERNS if p in lowered]

    def is_instruction_like(self, text: str) -> bool:
        """True if ``text`` contains any instruction-like pattern."""
        return bool(self.scan(text))

    def sanitize(self, text: str) -> str:
        """Return a data-safe rendering of ``text``.

        Neutralizes instruction-like phrasing so the text cannot be
        reinterpreted as a command. The original content is preserved as data
        where possible; detected instruction tokens are flagged.
        """
        result = text
        for pattern in self.INJECTION_PATTERNS:
            tagged = f"[{pattern.upper().replace(' ', '_')}_NEUTRALIZED]"
            result = result.replace(pattern, tagged)
            result = result.replace(pattern.capitalize(), tagged)
        return result


class InMemoryRunStore:
    """Thread-unsafe in-memory store of :class:`AgentRunRecord` keyed by run id.

    Also tracks idempotency keys so repeated side-effect calls return the
    recorded result instead of re-executing.
    """

    def __init__(self) -> None:
        self._runs: dict[str, AgentRunRecord] = {}
        self._idempotency: dict[str, str] = {}  # idempotency_key -> run_id

    def record(self, run: AgentRunRecord) -> None:
        self._runs[run.run_id] = run

    def get(self, run_id: str) -> AgentRunRecord | None:
        return self._runs.get(run_id)

    def register_idempotency(self, key: str, run_id: str) -> None:
        self._idempotency[key] = run_id

    def lookup_idempotency(self, key: str) -> str | None:
        return self._idempotency.get(key)

    def list(self) -> list[AgentRunRecord]:
        return list(self._runs.values())


class BaseAgent(Generic[InputT, OutputT], ABC):
    """Abstract base class for EquiTask AI agent adapters.

    Concrete agents implement :meth:`_execute`. :meth:`run` orchestrates the
    full contract:

        typed input
        -> untrusted-text guard (OWASP LLM01)
        -> execute with retries + backoff
        -> schema validation
        -> policy validation (ValidationGate)
        -> human approval (if consequential)
        -> service call / side effect
        -> record AgentRun

    Any invalid output writes ``AgentRun(status=INVALID_OUTPUT)``, raises, and
    performs no state change and no side effect.
    """

    #: The :class:`AgentType` this agent handles (set by subclasses).
    agent_type: AgentType
    #: Declared permission scope (set by subclasses or constructor).
    permission_scope: PermissionScope
    #: Runtime budget and policy (set by subclasses or constructor).
    config: AgentConfig

    #: Pydantic model class for typed input (set by subclasses).
    input_model: type[InputT] | None = None
    #: Pydantic model class for typed output (set by subclasses).
    output_model: type[OutputT] | None = None

    def __init__(
        self,
        *,
        permission_scope: PermissionScope | None = None,
        config: AgentConfig | None = None,
        store: InMemoryRunStore | None = None,
        gate: "ValidationGate | None" = None,
    ) -> None:
        self.permission_scope = permission_scope or self._default_scope()
        self.config = config or AgentConfig()
        self.store = store or InMemoryRunStore()
        self.gate = gate
        self._guard = PromptInjectionGuard()

    @classmethod
    @abstractmethod
    def _default_scope(cls) -> PermissionScope:
        """Return the default permission scope for this agent type."""

    @abstractmethod
    def _execute(self, input: InputT) -> OutputT:
        """Pure agent logic.

        Must perform no side effects. Receives a validated, typed input and
        returns a typed output. Untrusted text inside ``input`` must be treated
        as data via :attr:`_guard`, never as instructions.
        """

    def run(
        self,
        input: InputT,
        *,
        trace_id: str | None = None,
        idempotency_key: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> AgentRunResult[OutputT]:
        """Execute the full agent contract.

        Returns the typed output on success. Raises :class:`InvalidOutputError`,
        :class:`PendingApprovalError`, or :class:`AgentRunError` on failure; in
        all failure cases an AgentRun record is written and no side effect
        occurs.

        Args:
            input: Typed Pydantic input.
            trace_id: Optional correlation trace id; generated if omitted.
            idempotency_key: Optional key that makes a side-effecting run
                replay-safe; replays return the recorded result.
            context: Extra context passed to the validation gate (e.g. actor,
                organization, consequential action name).
        """
        trace_id = trace_id or f"trace_{uuid.uuid4().hex}"
        context = context or {}

        # Validate typed input before doing any work.
        if self.input_model is not None and not isinstance(input, self.input_model):
            try:
                input = self.input_model.model_validate(input)  # type: ignore[arg-type]
            except ValidationError as exc:
                raise InvalidOutputError(f"input schema validation failed: {exc}") from exc

        # Idempotency: replay an already-recorded side effect without
        # re-executing and without creating a second side effect.
        if idempotency_key:
            prior_run_id = self.store.lookup_idempotency(idempotency_key)
            if prior_run_id is not None:
                prior = self.store.get(prior_run_id)
                if prior is not None:
                    output = self._coerce_output(prior)
                    return AgentRunResult(
                        output=output,
                        run=prior,
                        status=prior.status,
                    )

        last_error: str | None = None
        output: OutputT | None = None
        run: AgentRunRecord | None = None

        for attempt in range(self.config.max_retries + 1):
            try:
                output = self._execute(input)
            except Exception as exc:  # noqa: BLE001
                last_error = f"execute error: {exc}"
                if attempt < self.config.max_retries:
                    self._sleep(attempt)
                    continue
                run = self._record(
                    trace_id,
                    AgentStatus.FAILED,
                    input,
                    None,
                    error=last_error,
                    context=context,
                )
                raise AgentRunError(last_error) from exc

            # Schema validation gate.
            try:
                self._validate_output_schema(output)
            except ValidationError as exc:
                last_error = f"schema validation failed: {exc}"
                if attempt < self.config.max_retries:
                    self._sleep(attempt)
                    continue
                run = self._record(
                    trace_id,
                    AgentStatus.INVALID_OUTPUT,
                    input,
                    None,
                    error=last_error,
                    context=context,
                )
                raise InvalidOutputError(last_error) from exc

            # Policy validation gate (schema -> policy -> approval -> service).
            try:
                self._apply_gate(output, input, context)
            except PendingApprovalError as exc:
                run = self._record(
                    trace_id,
                    AgentStatus.PENDING_APPROVAL,
                    input,
                    output,
                    error=str(exc),
                    context=context,
                )
                raise
            except InvalidOutputError as exc:
                last_error = str(exc)
                if attempt < self.config.max_retries:
                    self._sleep(attempt)
                    continue
                run = self._record(
                    trace_id,
                    AgentStatus.INVALID_OUTPUT,
                    input,
                    None,
                    error=last_error,
                    context=context,
                )
                raise
            except AgentRunError as exc:
                last_error = str(exc)
                run = self._record(
                    trace_id,
                    AgentStatus.REJECTED,
                    input,
                    None,
                    error=last_error,
                    context=context,
                )
                raise

            # Success: record COMPLETED and return output. Any side effect was
            # already performed by the gate's service call when the action is
            # consequential; otherwise recording the run is the only effect.
            run = self._record(trace_id, AgentStatus.COMPLETED, input, output, context=context)
            if idempotency_key and run is not None:
                self.store.register_idempotency(idempotency_key, run.run_id)
            return AgentRunResult(output=output, run=run, status=AgentStatus.COMPLETED)

        # Defensive; the loop always returns or raises before reaching here.
        run = self._record(
            trace_id,
            AgentStatus.FAILED,
            input,
            None,
            error=last_error or "unknown failure",
            context=context,
        )
        raise AgentRunError(last_error or "unknown failure")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _sleep(self, attempt: int) -> None:
        delay = self.config.backoff_base_seconds * (2**attempt)
        time.sleep(min(delay, self.config.timeout_seconds))

    def _validate_output_schema(self, output: OutputT) -> None:
        """Re-validate the typed output against its Pydantic output model."""
        if self.output_model is None:
            return
        self.output_model.model_validate(output)

    def _apply_gate(
        self,
        output: OutputT,
        input: InputT,
        context: dict[str, Any],
    ) -> None:
        """Run schema -> policy -> (approval) -> service validation gate."""
        if self.gate is None:
            return
        self.gate.validate(output=output, agent=self, input=input, context=context)

    def _record(
        self,
        trace_id: str,
        status: AgentStatus,
        input: InputT | None,
        output: OutputT | None,
        *,
        error: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> AgentRunRecord:
        output_json = None
        output_ref = None
        if output is not None:
            try:
                output_json = output.model_dump_json()
            except Exception:  # pragma: no cover - defensive
                output_json = None
            output_ref = str(output)[:200]
        input_ref = str(input)[:200] if input is not None else None
        run = AgentRunRecord(
            run_id=f"agn_{uuid.uuid4().hex}",
            agent_type=self.agent_type,
            status=status,
            input_ref=input_ref,
            output_ref=output_ref,
            output_json=output_json,
            policy_version=self.config.policy_version,
            trace_id=trace_id,
            error=error,
        )
        self.store.record(run)
        return run

    def _coerce_output(self, run: AgentRunRecord) -> OutputT:
        """Reconstruct a typed output from a recorded run (idempotent replay)."""
        if self.output_model is not None and run.output_json:
            return self.output_model.model_validate_json(run.output_json)  # type: ignore[return-value]
        # Fallback: cannot reconstruct; return the record itself as a placeholder.
        return run  # type: ignore[return-value]

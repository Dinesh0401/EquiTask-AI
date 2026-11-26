"""Agent registry for looking up agent adapters by type.

The registry maps :class:`~app.enums.AgentType` values to concrete
:class:`~app.agents.base.BaseAgent` subclasses. Agents register themselves
(or are registered by the application) so callers can obtain an agent
without importing every agent module.
"""

from __future__ import annotations

from typing import TypeVar

from ..enums import AgentType
from .base import BaseAgent

AgentT = TypeVar("AgentT", bound=BaseAgent)


class AgentRegistry:
    """Mutable registry of agent adapters keyed by :class:`AgentType`.

    Example::

        registry = AgentRegistry()
        registry.register(AgentType.TASK_INTAKE, TaskIntakeAgent)
        agent = registry.get(AgentType.TASK_INTAKE)(...)
    """

    def __init__(self) -> None:
        self._agents: dict[AgentType, type[BaseAgent]] = {}

    def register(self, agent_type: AgentType, agent_cls: type[BaseAgent]) -> None:
        """Register ``agent_cls`` for ``agent_type``.

        Raises:
            ValueError: if ``agent_type`` is already registered.
        """
        if agent_type in self._agents:
            raise ValueError(f"Agent type {agent_type.value} is already registered")
        self._agents[agent_type] = agent_cls

    def get(self, agent_type: AgentType) -> type[BaseAgent]:
        """Return the registered agent class for ``agent_type``.

        Raises:
            KeyError: if no agent is registered for ``agent_type``.
        """
        if agent_type not in self._agents:
            raise KeyError(f"No agent registered for {agent_type.value}")
        return self._agents[agent_type]

    def contains(self, agent_type: AgentType) -> bool:
        return agent_type in self._agents

    def list(self) -> list[AgentType]:
        return list(self._agents.keys())

    def unregister(self, agent_type: AgentType) -> bool:
        """Remove the registration for ``agent_type``. Returns True if removed."""
        if agent_type in self._agents:
            del self._agents[agent_type]
            return True
        return False

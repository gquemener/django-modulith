"""Public API of the support_team module.

This is the only entry point other modules are allowed to import (enforced by
import-linter). It exposes plain immutable DTOs, never Django models.
"""

import random
from collections.abc import Collection
from dataclasses import dataclass
from uuid import UUID

from .models import Agent


@dataclass(frozen=True)
class AgentInfo:
    id: UUID
    display_name: str
    is_manager: bool
    manager_id: UUID | None


def _to_info(agent: Agent) -> AgentInfo:
    return AgentInfo(
        id=agent.pk,
        display_name=str(agent),
        is_manager=agent.role == Agent.Role.MANAGER,
        manager_id=agent.manager_id,
    )


def get_agent(agent_id: UUID) -> AgentInfo | None:
    agent = Agent.objects.select_related("user").filter(pk=agent_id).first()
    return _to_info(agent) if agent else None


def is_support_staff(user_id: UUID) -> bool:
    return Agent.objects.filter(pk=user_id).exists()


def pick_available_agent(exclude: Collection[UUID] = ()) -> AgentInfo | None:
    """Pick an available front-line agent, excluding the given ones."""
    candidates = list(
        Agent.objects.select_related("user")
        .filter(role=Agent.Role.AGENT, is_available=True)
        .exclude(pk__in=list(exclude))
    )
    return _to_info(random.choice(candidates)) if candidates else None


def display_names(ids: Collection[UUID]) -> dict[UUID, str]:
    """Display names of support staff, by id."""
    return {
        agent.pk: str(agent)
        for agent in Agent.objects.select_related("user").filter(pk__in=list(ids))
    }

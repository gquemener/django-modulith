"""Adapters implementing the application ports with Django and other modules."""

import logging
from collections.abc import Collection
from contextlib import AbstractContextManager
from datetime import datetime
from uuid import UUID

from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from modules.accounts import api as accounts
from modules.shared.bus import EventBus
from modules.support_team import api as support_team

from ..domain import AgentId, Assignment
from ..domain.events import DomainEvent

logger = logging.getLogger(__name__)


class SystemClock:
    def now(self) -> datetime:
        return timezone.now()


class DjangoTransactionManager:
    def atomic(self) -> AbstractContextManager:
        return transaction.atomic()


class SupportTeamAgentDirectory:
    """Anti-corruption layer over the support_team module's public API."""

    def assign_agent(self, exclude: Collection[UUID] = ()) -> Assignment | None:
        agent = support_team.pick_available_agent(exclude=exclude)
        if agent is None:
            return None
        return Assignment(agent_id=AgentId(agent.id), manager_id=agent.manager_id)

    def is_support_staff(self, user_id: UUID) -> bool:
        return support_team.is_support_staff(user_id)

    def email_of(self, agent_id: UUID) -> str | None:
        return accounts.email_of(agent_id)


class DjangoEmailSender:
    def send(self, to: str, subject: str, body: str) -> None:
        send_mail(subject, body, None, [to])  # from DEFAULT_FROM_EMAIL


class BusEventPublisher:
    """Publishes domain events on the application-wide bus (delivered after commit)."""

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus

    def publish(self, events: list[DomainEvent]) -> None:
        for event in events:
            self._bus.publish(event)

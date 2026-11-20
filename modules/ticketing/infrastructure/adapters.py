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
from modules.support_team import api as support_team

from ..application.handlers import EventHandlers
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


class DispatchingEventPublisher:
    """Dispatches domain events to their handlers once the transaction commits.

    Handlers run in-process, after commit: a rolled-back use case notifies no one,
    and a failing handler is logged without affecting the others nor the caller.
    Swap for an outbox / message bus when delivery must be guaranteed.
    """

    def __init__(self, handlers: EventHandlers) -> None:
        self._handlers = handlers

    def publish(self, events: list[DomainEvent]) -> None:
        for event in events:
            transaction.on_commit(lambda e=event: self._dispatch(e))

    def _dispatch(self, event: DomainEvent) -> None:
        logger.info("Domain event: %r", event)
        for handler in self._handlers.get(type(event), ()):
            try:
                handler(event)
            except Exception:
                logger.exception("Handler %r failed on %r", handler, event)

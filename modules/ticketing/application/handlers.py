"""Domain event handlers: side effects triggered by what happened to a ticket.

Like use cases, they only talk to the outside world through ports.
"""

import logging
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from ..domain.events import DomainEvent, TicketOpened
from .ports import AgentDirectory, EmailSender

logger = logging.getLogger(__name__)

EventHandler = Callable[[Any], None]
EventHandlers = Mapping[type[DomainEvent], Sequence[EventHandler]]


class NotifyAgentOfNewTicket:
    """Emails the agent a newly opened ticket has been assigned to."""

    def __init__(self, agents: AgentDirectory, mailer: EmailSender) -> None:
        self._agents = agents
        self._mailer = mailer

    def __call__(self, event: TicketOpened) -> None:
        email = self._agents.email_of(event.agent_id)
        if email is None:
            logger.warning("Agent %s has no email; not notified of ticket %s", event.agent_id, event.ticket_id)
            return
        self._mailer.send(
            to=email,
            subject=f"New ticket assigned to you: {event.title}",
            body=(
                f"A customer opened a ticket that is now assigned to you.\n\n"
                f"Title: {event.title}\n"
                f"Priority: {event.priority}\n"
                f"Ticket: {event.ticket_id}\n"
            ),
        )

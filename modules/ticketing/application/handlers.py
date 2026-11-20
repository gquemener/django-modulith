"""Domain event handlers: side effects triggered by what happened to a ticket.

Like use cases, they only talk to the outside world through ports.
"""

import logging
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from ..domain.events import DomainEvent, ReassignmentReason, TicketOpened, TicketReassigned
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


_REASONS = {
    ReassignmentReason.ESCALATION_NOT_OPENED: "its escalation was not handled in time by the previous agent",
    ReassignmentReason.AGENT_SUSPENDED: "the previous agent was suspended",
}


class NotifyAgentOfReassignedTicket:
    """Emails the agent a ticket has just been reassigned to."""

    def __init__(self, agents: AgentDirectory, mailer: EmailSender) -> None:
        self._agents = agents
        self._mailer = mailer

    def __call__(self, event: TicketReassigned) -> None:
        email = self._agents.email_of(event.new_agent_id)
        if email is None:
            logger.warning(
                "Agent %s has no email; not notified of ticket %s", event.new_agent_id, event.ticket_id
            )
            return
        self._mailer.send(
            to=email,
            subject=f"Ticket reassigned to you: {event.title}",
            body=(
                f"A ticket has been reassigned to you because {_REASONS[event.reason]}.\n\n"
                f"Title: {event.title}\n"
                f"Ticket: {event.ticket_id}\n"
            ),
        )

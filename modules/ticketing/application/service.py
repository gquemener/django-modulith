"""Ticketing use cases.

Each method is one transaction: load the aggregate, ask it to do something,
save it, publish the events it recorded. No business rule lives here.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from ..domain import (
    CustomerId,
    InvalidTicketState,
    Priority,
    Ticket,
    TicketDomainError,
    TicketId,
    TicketRepository,
)
from ..domain.sla import AUTO_CLOSE_AFTER
from .ports import AgentDirectory, Clock, EventPublisher, TransactionManager

logger = logging.getLogger(__name__)


class NoAgentAvailable(InvalidTicketState):
    pass


class NotACustomer(TicketDomainError):
    pass


@dataclass(frozen=True)
class PolicyRunReport:
    closed: list[TicketId]
    reassigned: list[TicketId]


class TicketingService:
    def __init__(
        self,
        tickets: TicketRepository,
        agents: AgentDirectory,
        clock: Clock,
        publisher: EventPublisher,
        transactions: TransactionManager,
    ) -> None:
        self._tickets = tickets
        self._agents = agents
        self._clock = clock
        self._publisher = publisher
        self._transactions = transactions

    # ------------------------------------------------------------ commands

    def open_ticket(
        self, customer_id: UUID, title: str, description: str, priority: Priority
    ) -> TicketId:
        if self._agents.is_support_staff(customer_id):
            raise NotACustomer("Support staff cannot open tickets as customers.")
        with self._transactions.atomic():
            assignment = self._agents.assign_agent()
            if assignment is None:
                raise NoAgentAvailable("No support agent is available right now.")
            ticket = Ticket.open(
                ticket_id=self._tickets.next_identity(),
                customer_id=CustomerId(customer_id),
                title=title,
                description=description,
                priority=Priority(priority),
                assignment=assignment,
                now=self._clock.now(),
            )
            self._save(ticket)
        return ticket.id

    def post_message(self, ticket_id: TicketId, author_id: UUID, body: str) -> None:
        self._change(ticket_id, lambda t, now: t.post_message(author_id, body, now))

    def escalate(self, ticket_id: TicketId, customer_id: UUID) -> None:
        self._change(ticket_id, lambda t, now: t.escalate(customer_id, now))

    def record_opened(self, ticket_id: TicketId, viewer_id: UUID) -> None:
        self._change(ticket_id, lambda t, now: t.mark_opened_by(viewer_id, now))

    def close(self, ticket_id: TicketId, by: UUID) -> None:
        self._change(ticket_id, lambda t, now: t.close(by, now))

    def reopen(self, ticket_id: TicketId, customer_id: UUID) -> None:
        self._change(ticket_id, lambda t, now: t.reopen(customer_id, now))

    # ----------------------------------------------------- automatic policies

    def run_policies(self) -> PolicyRunReport:
        """Apply time-based rules. Meant to run periodically (cron, worker...)."""
        now = self._clock.now()
        closed, reassigned = [], []

        for ticket_id in self._tickets.ids_awaiting_customer_since(before=now - AUTO_CLOSE_AFTER):
            if self._try(ticket_id, self._close_if_due):
                closed.append(ticket_id)

        for ticket_id in self._tickets.ids_of_escalated_unopened():
            if self._try(ticket_id, self._reassign_if_due):
                reassigned.append(ticket_id)

        return PolicyRunReport(closed=closed, reassigned=reassigned)

    def _close_if_due(self, ticket: Ticket, now) -> bool:
        if not ticket.is_auto_close_due(now):
            return False
        ticket.close_for_inactivity(now)
        return True

    def _reassign_if_due(self, ticket: Ticket, now) -> bool:
        if not ticket.is_reassignment_due(now):
            return False
        assignment = self._agents.assign_agent(exclude={ticket.agent_id})
        if assignment is None:
            logger.warning("No agent available to reassign ticket %s", ticket.id)
            return False
        ticket.reassign(assignment, now)
        return True

    # ---------------------------------------------------------------- helpers

    def _try(self, ticket_id: TicketId, action: Callable[[Ticket, object], bool]) -> bool:
        try:
            return self._change(ticket_id, action)
        except Exception:
            logger.exception("Policy failed for ticket %s", ticket_id)
            return False

    def _change(self, ticket_id: TicketId, action: Callable[[Ticket, object], object]):
        with self._transactions.atomic():
            ticket = self._tickets.get(ticket_id)
            result = action(ticket, self._clock.now())
            self._save(ticket)
        return result

    def _save(self, ticket: Ticket) -> None:
        events = ticket.pull_events()
        if events:
            self._tickets.save(ticket)
            self._publisher.publish(events)

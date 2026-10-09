"""Ticket aggregate.

Pure Python: no Django import is allowed in this package (enforced by
import-linter). Time is always passed in as `now` so every rule is
deterministic and trivially testable.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import NewType
from uuid import UUID

from . import events
from .exceptions import (
    ActionNotAllowed,
    EscalationNotAllowed,
    InvalidTicketState,
    ReassignmentNotAllowed,
    ReopenWindowExpired,
    TicketDomainError,
)
from .sla import (
    AUTO_CLOSE_AFTER,
    REASSIGNMENT_RATIO,
    REOPEN_WINDOW,
    Priority,
    response_time_limit,
)

TicketId = NewType("TicketId", UUID)
CustomerId = NewType("CustomerId", UUID)
AgentId = NewType("AgentId", UUID)


class TicketStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class AuthorRole(StrEnum):
    CUSTOMER = "customer"
    AGENT = "agent"


@dataclass(frozen=True)
class Message:
    id: UUID
    author_role: AuthorRole
    author_id: UUID
    body: str
    sent_at: datetime


@dataclass(frozen=True)
class Assignment:
    """An agent and the manager tickets escalate to."""

    agent_id: AgentId
    manager_id: UUID | None


class Ticket:
    """Aggregate root guarding the whole lifecycle of a support ticket.

    State that drives the time-based rules is explicit rather than derived:
    - `awaiting_agent_since`: start of the agent's SLA clock (None when the
      ball is in the customer's court);
    - `awaiting_customer_since`: when the agent last asked the customer
      something (drives the 7-day automatic closing);
    - `escalated_at` / `opened_by_agent_since_escalation`: drive escalation
      and automatic reassignment.
    """

    def __init__(
        self,
        *,
        id: TicketId,
        customer_id: CustomerId,
        title: str,
        priority: Priority,
        assignment: Assignment,
        assigned_at: datetime,
        opened_at: datetime,
        status: TicketStatus = TicketStatus.OPEN,
        messages: list[Message] | None = None,
        awaiting_agent_since: datetime | None = None,
        awaiting_customer_since: datetime | None = None,
        escalated_at: datetime | None = None,
        opened_by_agent_since_escalation: bool = False,
        closed_at: datetime | None = None,
        version: int = 0,
    ) -> None:
        self.id = id
        self.customer_id = customer_id
        self.title = title
        self.priority = priority
        self.assignment = assignment
        self.assigned_at = assigned_at
        self.opened_at = opened_at
        self.status = status
        self._messages = list(messages or [])
        self.awaiting_agent_since = awaiting_agent_since
        self.awaiting_customer_since = awaiting_customer_since
        self.escalated_at = escalated_at
        self.opened_by_agent_since_escalation = opened_by_agent_since_escalation
        self.closed_at = closed_at
        # Used by the repository for optimistic concurrency control.
        self.version = version
        self._pending_events: list[events.DomainEvent] = []

    # ------------------------------------------------------------------ factory

    @classmethod
    def open(
        cls,
        *,
        ticket_id: TicketId,
        customer_id: CustomerId,
        title: str,
        description: str,
        priority: Priority,
        assignment: Assignment,
        now: datetime,
    ) -> Ticket:
        """A customer opens a ticket describing the issue they are facing."""
        title = title.strip()
        if not title:
            raise InvalidTicketState("A ticket needs a title.")
        ticket = cls(
            id=ticket_id,
            customer_id=customer_id,
            title=title,
            priority=priority,
            assignment=assignment,
            assigned_at=now,
            opened_at=now,
        )
        ticket._record(events.TicketOpened(
            ticket_id=ticket_id, occurred_at=now, customer_id=customer_id,
            agent_id=assignment.agent_id, priority=priority,
        ))
        ticket._append(AuthorRole.CUSTOMER, customer_id, description, now)
        return ticket

    # --------------------------------------------------------------- read state

    @property
    def messages(self) -> tuple[Message, ...]:
        return tuple(self._messages)

    @property
    def agent_id(self) -> AgentId:
        return self.assignment.agent_id

    @property
    def manager_id(self) -> UUID | None:
        return self.assignment.manager_id

    @property
    def is_open(self) -> bool:
        return self.status is TicketStatus.OPEN

    @property
    def is_escalated(self) -> bool:
        return self.escalated_at is not None

    @property
    def response_time_limit(self):
        return response_time_limit(self.priority, escalated=self.is_escalated)

    @property
    def response_deadline(self) -> datetime | None:
        """When the agent must have answered, or None if nothing is pending.

        After an escalation (or a reassignment) the agent gets a fresh,
        reduced, time limit starting at that moment.
        """
        if not self.is_open or self.awaiting_agent_since is None:
            return None
        starts = [self.awaiting_agent_since]
        if self.escalated_at is not None:
            starts += [self.escalated_at, self.assigned_at]
        return max(starts) + self.response_time_limit

    @property
    def reassignment_deadline(self) -> datetime | None:
        """When an escalated ticket not yet opened by its agent gets reassigned."""
        if not (self.is_open and self.is_escalated) or self.opened_by_agent_since_escalation:
            return None
        since = max(self.escalated_at, self.assigned_at)
        return since + self.response_time_limit * REASSIGNMENT_RATIO

    @property
    def auto_close_at(self) -> datetime | None:
        if not self.is_open or self.is_escalated or self.awaiting_customer_since is None:
            return None
        return self.awaiting_customer_since + AUTO_CLOSE_AFTER

    @property
    def reopen_deadline(self) -> datetime | None:
        return self.closed_at + REOPEN_WINDOW if self.closed_at and not self.is_open else None

    # ------------------------------------------------------------- correspondence

    def post_message(self, author_id: UUID, body: str, now: datetime) -> None:
        """Customer and assigned agent append messages to the correspondence."""
        self._ensure_open()
        if author_id == self.customer_id:
            role = AuthorRole.CUSTOMER
        elif author_id == self.agent_id:
            role = AuthorRole.AGENT
        else:
            raise ActionNotAllowed("Only the customer and the assigned agent can post messages.")
        self._append(role, author_id, body, now)

    def _append(self, role: AuthorRole, author_id: UUID, body: str, now: datetime) -> None:
        body = body.strip()
        if not body:
            raise InvalidTicketState("A message cannot be empty.")
        message = Message(id=uuid.uuid4(), author_role=role, author_id=author_id, body=body, sent_at=now)
        self._messages.append(message)
        if role is AuthorRole.CUSTOMER:
            # The SLA clock starts at the first unanswered customer message.
            if self.awaiting_agent_since is None:
                self.awaiting_agent_since = now
            self.awaiting_customer_since = None
        else:
            self.awaiting_agent_since = None
            self.awaiting_customer_since = now
        self._record(events.MessagePosted(
            ticket_id=self.id, occurred_at=now, message_id=message.id,
            author_role=role.value, author_id=author_id,
        ))

    # ----------------------------------------------------------------- escalation

    def escalate(self, by: UUID, now: datetime) -> None:
        self._check_escalate(by, now)
        self.escalated_at = now
        self.opened_by_agent_since_escalation = False
        self._record(events.TicketEscalated(
            ticket_id=self.id, occurred_at=now, agent_id=self.agent_id, manager_id=self.manager_id,
        ))

    def can_escalate(self, by: UUID, now: datetime) -> bool:
        return self._passes(self._check_escalate, by, now)

    def _check_escalate(self, by: UUID, now: datetime) -> None:
        self._ensure_open()
        if by != self.customer_id:
            raise ActionNotAllowed("Only the customer can escalate a ticket.")
        if self.is_escalated:
            raise EscalationNotAllowed("The ticket is already escalated.")
        deadline = self.response_deadline
        if deadline is None or now <= deadline:
            raise EscalationNotAllowed("The agent is still within the response time limit.")
        if self.manager_id is None:
            raise EscalationNotAllowed("The assigned agent has no manager to escalate to.")

    def mark_opened_by(self, viewer_id: UUID, now: datetime) -> None:
        """Record that the assigned agent opened the ticket."""
        if (
            viewer_id == self.agent_id
            and self.is_open
            and self.is_escalated
            and not self.opened_by_agent_since_escalation
        ):
            self.opened_by_agent_since_escalation = True
            self._record(events.EscalatedTicketOpenedByAgent(
                ticket_id=self.id, occurred_at=now, agent_id=self.agent_id,
            ))

    def is_reassignment_due(self, now: datetime) -> bool:
        deadline = self.reassignment_deadline
        return deadline is not None and now >= deadline

    def reassign(self, assignment: Assignment, now: datetime) -> None:
        """Hand an escalated ticket the agent did not open in time to someone else."""
        if not self.is_reassignment_due(now):
            raise ReassignmentNotAllowed("The ticket is not due for reassignment.")
        if assignment.agent_id == self.agent_id:
            raise ReassignmentNotAllowed("The ticket must be reassigned to a different agent.")
        previous = self.agent_id
        self.assignment = assignment
        self.assigned_at = now
        self.opened_by_agent_since_escalation = False
        self._record(events.TicketReassigned(
            ticket_id=self.id, occurred_at=now, previous_agent_id=previous, new_agent_id=assignment.agent_id,
        ))

    # -------------------------------------------------------------------- closing

    def close(self, by: UUID, now: datetime) -> None:
        self._check_close(by)
        self._close(now, closed_by=by)

    def can_close(self, by: UUID) -> bool:
        return self._passes(self._check_close, by)

    def _check_close(self, by: UUID) -> None:
        self._ensure_open()
        allowed = {self.customer_id, self.manager_id}
        if not self.is_escalated:
            allowed.add(self.agent_id)
        if by not in allowed:
            if self.is_escalated and by == self.agent_id:
                raise ActionNotAllowed(
                    "An escalated ticket can only be closed by the customer or the agent's manager."
                )
            raise ActionNotAllowed("You are not allowed to close this ticket.")

    def is_auto_close_due(self, now: datetime) -> bool:
        deadline = self.auto_close_at
        return deadline is not None and now >= deadline

    def close_for_inactivity(self, now: datetime) -> None:
        """Close the ticket when the customer did not reply within seven days."""
        if not self.is_auto_close_due(now):
            raise InvalidTicketState("The ticket cannot be closed automatically.")
        self._close(now, closed_by=None)

    def _close(self, now: datetime, closed_by: UUID | None) -> None:
        self.status = TicketStatus.CLOSED
        self.closed_at = now
        self._record(events.TicketClosed(ticket_id=self.id, occurred_at=now, closed_by=closed_by))

    # ------------------------------------------------------------------ reopening

    def reopen(self, by: UUID, now: datetime) -> None:
        self._check_reopen(by, now)
        self.status = TicketStatus.OPEN
        self.closed_at = None
        # A reopened ticket starts a fresh cycle: the agent owes an answer.
        self.escalated_at = None
        self.opened_by_agent_since_escalation = False
        self.awaiting_customer_since = None
        self.awaiting_agent_since = now
        self._record(events.TicketReopened(ticket_id=self.id, occurred_at=now))

    def can_reopen(self, by: UUID, now: datetime) -> bool:
        return self._passes(self._check_reopen, by, now)

    def _check_reopen(self, by: UUID, now: datetime) -> None:
        if self.is_open:
            raise InvalidTicketState("The ticket is not closed.")
        if by != self.customer_id:
            raise ActionNotAllowed("Only the customer can reopen a ticket.")
        if now > self.reopen_deadline:
            raise ReopenWindowExpired("A ticket can only be reopened within seven days of being closed.")

    # -------------------------------------------------------------------- helpers

    def pull_events(self) -> list[events.DomainEvent]:
        pending, self._pending_events = self._pending_events, []
        return pending

    def _record(self, event: events.DomainEvent) -> None:
        self._pending_events.append(event)

    def _ensure_open(self) -> None:
        if not self.is_open:
            raise InvalidTicketState("The ticket is closed.")

    @staticmethod
    def _passes(check, *args) -> bool:
        try:
            check(*args)
        except TicketDomainError:
            return False
        return True

    def __repr__(self) -> str:
        return f"<Ticket {self.id} {self.status} priority={self.priority}>"

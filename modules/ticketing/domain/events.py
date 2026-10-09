"""Domain events recorded by the Ticket aggregate."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, kw_only=True)
class DomainEvent:
    ticket_id: UUID
    occurred_at: datetime


@dataclass(frozen=True, kw_only=True)
class TicketOpened(DomainEvent):
    customer_id: UUID
    agent_id: UUID
    priority: str


@dataclass(frozen=True, kw_only=True)
class MessagePosted(DomainEvent):
    message_id: UUID
    author_role: str
    author_id: UUID


@dataclass(frozen=True, kw_only=True)
class TicketEscalated(DomainEvent):
    agent_id: UUID
    manager_id: UUID | None


@dataclass(frozen=True, kw_only=True)
class EscalatedTicketOpenedByAgent(DomainEvent):
    agent_id: UUID


@dataclass(frozen=True, kw_only=True)
class TicketReassigned(DomainEvent):
    previous_agent_id: UUID
    new_agent_id: UUID


@dataclass(frozen=True, kw_only=True)
class TicketClosed(DomainEvent):
    closed_by: UUID | None  # None when closed automatically


@dataclass(frozen=True, kw_only=True)
class TicketReopened(DomainEvent):
    pass

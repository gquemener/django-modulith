"""Ticketing domain model: framework-free business rules."""

from .exceptions import (
    ActionNotAllowed,
    EscalationNotAllowed,
    InvalidTicketState,
    ReassignmentNotAllowed,
    ReopenWindowExpired,
    TicketDomainError,
    TicketNotFound,
)
from .model import (
    AgentId,
    Assignment,
    AuthorRole,
    CustomerId,
    Message,
    Ticket,
    TicketId,
    TicketStatus,
)
from .repository import ConcurrencyConflict, TicketRepository
from .sla import Priority

__all__ = [
    "ActionNotAllowed",
    "AgentId",
    "Assignment",
    "AuthorRole",
    "ConcurrencyConflict",
    "CustomerId",
    "EscalationNotAllowed",
    "InvalidTicketState",
    "Message",
    "Priority",
    "ReassignmentNotAllowed",
    "ReopenWindowExpired",
    "Ticket",
    "TicketDomainError",
    "TicketId",
    "TicketNotFound",
    "TicketRepository",
    "TicketStatus",
]

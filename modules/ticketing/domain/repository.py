from abc import ABC, abstractmethod
from datetime import datetime

from .model import Ticket, TicketId


class TicketRepository(ABC):
    """Collection-like access to Ticket aggregates (implemented in infrastructure)."""

    @abstractmethod
    def next_identity(self) -> TicketId: ...

    @abstractmethod
    def get(self, ticket_id: TicketId) -> Ticket:
        """Raise TicketNotFound when there is no such ticket."""

    @abstractmethod
    def save(self, ticket: Ticket) -> None:
        """Persist the ticket; raise ConcurrencyConflict if it changed meanwhile."""

    @abstractmethod
    def ids_awaiting_customer_since(self, before: datetime) -> list[TicketId]:
        """Open, non-escalated tickets the customer has not answered since `before`."""

    @abstractmethod
    def ids_of_escalated_unopened(self) -> list[TicketId]:
        """Open escalated tickets their agent has not opened yet."""


class ConcurrencyConflict(Exception):
    """The aggregate was modified by someone else since it was loaded."""

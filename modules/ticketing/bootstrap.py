"""Composition root of the ticketing module."""

from .application.service import TicketingService
from .infrastructure.adapters import (
    DjangoTransactionManager,
    LoggingEventPublisher,
    SupportTeamAgentDirectory,
    SystemClock,
)
from .infrastructure.repository import DjangoTicketRepository


def ticketing_service() -> TicketingService:
    return TicketingService(
        tickets=DjangoTicketRepository(),
        agents=SupportTeamAgentDirectory(),
        clock=SystemClock(),
        publisher=LoggingEventPublisher(),
        transactions=DjangoTransactionManager(),
    )

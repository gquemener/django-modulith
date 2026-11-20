"""Composition root of the ticketing module."""

from .application.handlers import NotifyAgentOfNewTicket
from .application.service import TicketingService
from .domain.events import TicketOpened
from .infrastructure.adapters import (
    DispatchingEventPublisher,
    DjangoEmailSender,
    DjangoTransactionManager,
    SupportTeamAgentDirectory,
    SystemClock,
)
from .infrastructure.repository import DjangoTicketRepository


def ticketing_service() -> TicketingService:
    agents = SupportTeamAgentDirectory()
    return TicketingService(
        tickets=DjangoTicketRepository(),
        agents=agents,
        clock=SystemClock(),
        publisher=DispatchingEventPublisher({
            TicketOpened: [NotifyAgentOfNewTicket(agents, DjangoEmailSender())],
        }),
        transactions=DjangoTransactionManager(),
    )

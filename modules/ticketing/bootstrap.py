"""Composition root of the ticketing module."""

from modules.shared.bus import Handler, bus

from .application.handlers import NotifyAgentOfNewTicket, NotifyAgentOfReassignedTicket
from .application.service import TicketingService
from .infrastructure.adapters import (
    BusEventPublisher,
    DjangoEmailSender,
    DjangoTransactionManager,
    SupportTeamAgentDirectory,
    SystemClock,
)
from .infrastructure.repository import DjangoTicketRepository
from .infrastructure.subscribers import HandOverTicketsOfSuspendedAgent


def ticketing_service() -> TicketingService:
    return TicketingService(
        tickets=DjangoTicketRepository(),
        agents=SupportTeamAgentDirectory(),
        clock=SystemClock(),
        publisher=BusEventPublisher(bus),
        transactions=DjangoTransactionManager(),
    )


def event_handlers() -> list[Handler]:
    """Discovered at startup by modules.shared, which routes events on each handler's type hint."""
    agents = SupportTeamAgentDirectory()
    mailer = DjangoEmailSender()
    return [
        NotifyAgentOfNewTicket(agents, mailer),
        NotifyAgentOfReassignedTicket(agents, mailer),
        HandOverTicketsOfSuspendedAgent(ticketing_service()),
    ]

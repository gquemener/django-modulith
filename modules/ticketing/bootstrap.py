"""Composition root of the ticketing module."""

from modules.support_team import api as support_team

from .application.handlers import NotifyAgentOfNewTicket, NotifyAgentOfReassignedTicket
from .application.service import TicketingService
from .domain.events import TicketOpened, TicketReassigned
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
    mailer = DjangoEmailSender()
    return TicketingService(
        tickets=DjangoTicketRepository(),
        agents=agents,
        clock=SystemClock(),
        publisher=DispatchingEventPublisher({
            TicketOpened: [NotifyAgentOfNewTicket(agents, mailer)],
            TicketReassigned: [NotifyAgentOfReassignedTicket(agents, mailer)],
        }),
        transactions=DjangoTransactionManager(),
    )


# ----------------------------------------------- events from other modules


def on_agent_suspended(event: support_team.AgentSuspended) -> None:
    ticketing_service().hand_over_tickets_of(event.agent_id)


def subscribe_to_other_modules() -> None:
    """Called once at startup (TicketingConfig.ready)."""
    support_team.subscribe(support_team.AgentSuspended, on_agent_suspended)

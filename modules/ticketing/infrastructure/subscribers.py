"""Handlers of events published by other modules.

They live in infrastructure because they translate another module's public
events (anti-corruption layer) into ticketing use cases.
"""

from modules.support_team import api as support_team

from ..application.service import TicketingService


class HandOverTicketsOfSuspendedAgent:
    def __init__(self, service: TicketingService) -> None:
        self._service = service

    def __call__(self, event: support_team.AgentSuspended) -> None:
        self._service.hand_over_tickets_of(event.agent_id)

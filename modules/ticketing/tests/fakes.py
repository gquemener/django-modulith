"""In-memory adapters to test use cases without a database."""

import copy
import uuid
from contextlib import nullcontext

from modules.ticketing.domain import (
    AgentId,
    Assignment,
    ConcurrencyConflict,
    TicketId,
    TicketNotFound,
    TicketRepository,
)


class InMemoryTicketRepository(TicketRepository):
    def __init__(self):
        self.tickets = {}

    def next_identity(self):
        return TicketId(uuid.uuid4())

    def get(self, ticket_id):
        try:
            return copy.deepcopy(self.tickets[ticket_id])
        except KeyError:
            raise TicketNotFound(ticket_id) from None

    def save(self, ticket):
        stored = self.tickets.get(ticket.id)
        if (stored.version if stored else 0) != ticket.version:
            raise ConcurrencyConflict(ticket.id)
        ticket.version += 1
        self.tickets[ticket.id] = copy.deepcopy(ticket)

    def ids_awaiting_customer_since(self, before):
        return [
            t.id for t in self.tickets.values()
            if t.is_open and not t.is_escalated
            and t.awaiting_customer_since and t.awaiting_customer_since <= before
        ]

    def ids_of_escalated_unopened(self):
        return [
            t.id for t in self.tickets.values()
            if t.is_open and t.is_escalated and not t.opened_by_agent_since_escalation
        ]


class FakeAgentDirectory:
    def __init__(self, agents, manager_id=None, staff=()):
        self.agents = [AgentId(a) for a in agents]
        self.manager_id = manager_id
        self.staff = {*self.agents, *staff}

    def assign_agent(self, exclude=()):
        for agent in self.agents:
            if agent not in exclude:
                return Assignment(agent_id=agent, manager_id=self.manager_id)
        return None

    def is_support_staff(self, user_id):
        return user_id in self.staff


class FrozenClock:
    def __init__(self, now):
        self.current = now

    def now(self):
        return self.current

    def advance(self, delta):
        self.current += delta


class RecordingPublisher:
    def __init__(self):
        self.events = []

    def publish(self, events):
        self.events.extend(events)


class NoTransactions:
    def atomic(self):
        return nullcontext()

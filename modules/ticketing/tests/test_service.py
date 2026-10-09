"""Use cases wired to in-memory fakes: fast, no database."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from modules.ticketing.application.service import NoAgentAvailable, NotACustomer, TicketingService
from modules.ticketing.domain import ConcurrencyConflict, Priority, TicketStatus
from modules.ticketing.domain import events

from .fakes import FakeAgentDirectory, FrozenClock, InMemoryTicketRepository, NoTransactions, RecordingPublisher

ALICE, BOB, MARIA, CAROL = (uuid.uuid4() for _ in range(4))


@pytest.fixture
def clock():
    return FrozenClock(datetime(2026, 1, 5, 9, 0, tzinfo=UTC))


@pytest.fixture
def repo():
    return InMemoryTicketRepository()


@pytest.fixture
def publisher():
    return RecordingPublisher()


@pytest.fixture
def service(repo, clock, publisher):
    return TicketingService(
        tickets=repo,
        agents=FakeAgentDirectory([ALICE, BOB], manager_id=MARIA, staff=[MARIA]),
        clock=clock,
        publisher=publisher,
        transactions=NoTransactions(),
    )


def test_open_ticket_assigns_an_agent_and_publishes_events(service, repo, publisher):
    ticket_id = service.open_ticket(CAROL, "Bug", "It crashes", Priority.URGENT)

    ticket = repo.get(ticket_id)
    assert ticket.agent_id == ALICE
    assert ticket.manager_id == MARIA
    assert isinstance(publisher.events[0], events.TicketOpened)


def test_staff_cannot_open_tickets(service):
    with pytest.raises(NotACustomer):
        service.open_ticket(MARIA, "Bug", "x", Priority.LOW)


def test_open_ticket_requires_an_available_agent(repo, clock, publisher):
    service = TicketingService(repo, FakeAgentDirectory([]), clock, publisher, NoTransactions())
    with pytest.raises(NoAgentAvailable):
        service.open_ticket(CAROL, "Bug", "x", Priority.LOW)


def test_policies_reassign_unopened_escalated_tickets(service, repo, clock):
    ticket_id = service.open_ticket(CAROL, "Bug", "x", Priority.URGENT)
    clock.advance(timedelta(hours=2))
    service.escalate(ticket_id, CAROL)
    clock.advance(timedelta(minutes=21))  # > 50% of 1h * 0.67

    report = service.run_policies()

    assert report.reassigned == [ticket_id]
    assert repo.get(ticket_id).agent_id == BOB


def test_policies_leave_opened_escalated_tickets_alone(service, repo, clock):
    ticket_id = service.open_ticket(CAROL, "Bug", "x", Priority.URGENT)
    clock.advance(timedelta(hours=2))
    service.escalate(ticket_id, CAROL)
    service.record_opened(ticket_id, ALICE)
    clock.advance(timedelta(hours=1))

    assert service.run_policies().reassigned == []
    assert repo.get(ticket_id).agent_id == ALICE


def test_policies_close_tickets_the_customer_abandoned(service, repo, clock):
    ticket_id = service.open_ticket(CAROL, "Bug", "x", Priority.LOW)
    service.post_message(ticket_id, ALICE, "Screenshot please?")
    clock.advance(timedelta(days=7))

    assert service.run_policies().closed == [ticket_id]
    assert repo.get(ticket_id).status is TicketStatus.CLOSED


def test_recording_a_non_escalated_opening_is_a_no_op(service, repo, publisher):
    ticket_id = service.open_ticket(CAROL, "Bug", "x", Priority.LOW)
    version = repo.get(ticket_id).version
    publisher.events.clear()

    service.record_opened(ticket_id, ALICE)

    assert repo.get(ticket_id).version == version
    assert publisher.events == []


def test_concurrent_modifications_are_detected(service, repo):
    ticket_id = service.open_ticket(CAROL, "Bug", "x", Priority.LOW)
    stale = repo.get(ticket_id)
    service.post_message(ticket_id, ALICE, "Hello")

    stale.post_message(CAROL, "Me too", stale.opened_at)
    with pytest.raises(ConcurrencyConflict):
        repo.save(stale)

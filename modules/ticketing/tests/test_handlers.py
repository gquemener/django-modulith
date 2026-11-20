"""Event handlers wired to in-memory fakes: fast, no database."""

import uuid
from datetime import UTC, datetime

from modules.ticketing.application.handlers import NotifyAgentOfNewTicket, NotifyAgentOfReassignedTicket
from modules.ticketing.domain import Priority
from modules.ticketing.domain.events import ReassignmentReason, TicketOpened, TicketReassigned

from .fakes import FakeAgentDirectory, RecordingEmailSender

ALICE, BOB, CAROL = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


def ticket_opened(agent_id=ALICE):
    return TicketOpened(
        ticket_id=uuid.uuid4(),
        occurred_at=datetime(2026, 1, 5, 9, 0, tzinfo=UTC),
        customer_id=CAROL,
        agent_id=agent_id,
        title="Printer on fire",
        priority=Priority.URGENT,
    )


def test_assigned_agent_is_emailed_when_a_ticket_is_opened():
    mailer = RecordingEmailSender()
    handler = NotifyAgentOfNewTicket(FakeAgentDirectory([ALICE], emails={ALICE: "alice@example.com"}), mailer)
    event = ticket_opened()

    handler(event)

    [(to, subject, body)] = mailer.sent
    assert to == "alice@example.com"
    assert "Printer on fire" in subject
    assert "urgent" in body
    assert str(event.ticket_id) in body


def test_agent_without_email_is_not_notified():
    mailer = RecordingEmailSender()
    handler = NotifyAgentOfNewTicket(FakeAgentDirectory([ALICE]), mailer)

    handler(ticket_opened())

    assert mailer.sent == []


def test_new_agent_is_emailed_when_a_ticket_is_reassigned_to_them():
    mailer = RecordingEmailSender()
    handler = NotifyAgentOfReassignedTicket(FakeAgentDirectory([BOB], emails={BOB: "bob@example.com"}), mailer)

    handler(TicketReassigned(
        ticket_id=uuid.uuid4(),
        occurred_at=datetime(2026, 1, 5, 9, 0, tzinfo=UTC),
        previous_agent_id=ALICE,
        new_agent_id=BOB,
        title="Printer on fire",
        reason=ReassignmentReason.AGENT_SUSPENDED,
    ))

    [(to, subject, body)] = mailer.sent
    assert to == "bob@example.com"
    assert "Printer on fire" in subject
    assert "suspended" in body

"""Business rules, tested on the pure-Python aggregate: no database, no Django."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from modules.ticketing.domain import (
    ActionNotAllowed,
    AgentId,
    Assignment,
    CustomerId,
    EscalationNotAllowed,
    InvalidTicketState,
    Priority,
    ReassignmentNotAllowed,
    ReopenWindowExpired,
    Ticket,
    TicketId,
    TicketStatus,
)
from modules.ticketing.domain import events

T0 = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)
CUSTOMER = CustomerId(uuid.uuid4())
AGENT = AgentId(uuid.uuid4())
OTHER_AGENT = AgentId(uuid.uuid4())
MANAGER = uuid.uuid4()
STRANGER = uuid.uuid4()


def open_ticket(priority=Priority.HIGH, manager=MANAGER) -> Ticket:
    ticket = Ticket.open(
        ticket_id=TicketId(uuid.uuid4()),
        customer_id=CUSTOMER,
        title="Cannot log in",
        description="The login page shows an error.",
        priority=priority,
        assignment=Assignment(agent_id=AGENT, manager_id=manager),
        now=T0,
    )
    ticket.pull_events()
    return ticket


def escalated_ticket() -> Ticket:
    """HIGH priority: 4h SLA, escalated at T0+5h → reduced limit 2h40m."""
    ticket = open_ticket()
    ticket.escalate(CUSTOMER, T0 + timedelta(hours=5))
    return ticket


class TestOpening:
    def test_a_customer_opens_a_ticket_with_its_description_as_first_message(self):
        ticket = Ticket.open(
            ticket_id=TicketId(uuid.uuid4()), customer_id=CUSTOMER, title="Bug",
            description="It crashes", priority=Priority.LOW,
            assignment=Assignment(AGENT, MANAGER), now=T0,
        )
        assert ticket.status is TicketStatus.OPEN
        assert [m.body for m in ticket.messages] == ["It crashes"]
        assert [type(e) for e in ticket.pull_events()] == [events.TicketOpened, events.MessagePosted]

    def test_a_ticket_needs_a_title(self):
        with pytest.raises(InvalidTicketState):
            Ticket.open(
                ticket_id=TicketId(uuid.uuid4()), customer_id=CUSTOMER, title="  ",
                description="x", priority=Priority.LOW, assignment=Assignment(AGENT, MANAGER), now=T0,
            )


class TestCorrespondence:
    def test_customer_and_agent_append_messages(self):
        ticket = open_ticket()
        ticket.post_message(AGENT, "Which browser?", T0 + timedelta(minutes=5))
        ticket.post_message(CUSTOMER, "Firefox", T0 + timedelta(minutes=10))
        assert [m.author_role for m in ticket.messages] == ["customer", "agent", "customer"]

    def test_nobody_else_can_post(self):
        with pytest.raises(ActionNotAllowed):
            open_ticket().post_message(STRANGER, "Hi", T0)

    def test_messages_cannot_be_empty(self):
        with pytest.raises(InvalidTicketState):
            open_ticket().post_message(CUSTOMER, "   ", T0)

    def test_no_message_on_a_closed_ticket(self):
        ticket = open_ticket()
        ticket.close(CUSTOMER, T0)
        with pytest.raises(InvalidTicketState):
            ticket.post_message(CUSTOMER, "Hello?", T0)


class TestSla:
    @pytest.mark.parametrize("priority, hours", [
        (Priority.LOW, 24), (Priority.MEDIUM, 8), (Priority.HIGH, 4), (Priority.URGENT, 1),
    ])
    def test_response_deadline_depends_on_priority(self, priority, hours):
        assert open_ticket(priority).response_deadline == T0 + timedelta(hours=hours)

    def test_an_agent_reply_stops_the_clock(self):
        ticket = open_ticket()
        ticket.post_message(AGENT, "Looking into it", T0 + timedelta(hours=1))
        assert ticket.response_deadline is None

    def test_the_clock_starts_at_the_first_unanswered_customer_message(self):
        ticket = open_ticket()
        ticket.post_message(AGENT, "Which browser?", T0 + timedelta(hours=1))
        ticket.post_message(CUSTOMER, "Firefox", T0 + timedelta(hours=2))
        ticket.post_message(CUSTOMER, "Version 140", T0 + timedelta(hours=3))
        assert ticket.response_deadline == T0 + timedelta(hours=2 + 4)


class TestEscalation:
    def test_customer_can_escalate_once_the_sla_is_breached(self):
        ticket = open_ticket()
        assert not ticket.can_escalate(CUSTOMER, T0 + timedelta(hours=4))
        assert ticket.can_escalate(CUSTOMER, T0 + timedelta(hours=4, seconds=1))

        ticket.escalate(CUSTOMER, T0 + timedelta(hours=5))

        assert ticket.is_escalated
        assert isinstance(ticket.pull_events()[0], events.TicketEscalated)

    def test_cannot_escalate_within_the_sla(self):
        with pytest.raises(EscalationNotAllowed):
            open_ticket().escalate(CUSTOMER, T0 + timedelta(hours=1))

    def test_cannot_escalate_when_the_agent_replied(self):
        ticket = open_ticket()
        ticket.post_message(AGENT, "Done", T0 + timedelta(hours=1))
        with pytest.raises(EscalationNotAllowed):
            ticket.escalate(CUSTOMER, T0 + timedelta(hours=10))

    def test_only_the_customer_can_escalate(self):
        with pytest.raises(ActionNotAllowed):
            open_ticket().escalate(AGENT, T0 + timedelta(hours=5))

    def test_cannot_escalate_twice(self):
        with pytest.raises(EscalationNotAllowed):
            escalated_ticket().escalate(CUSTOMER, T0 + timedelta(hours=20))

    def test_cannot_escalate_without_a_manager(self):
        with pytest.raises(EscalationNotAllowed):
            open_ticket(manager=None).escalate(CUSTOMER, T0 + timedelta(hours=5))

    def test_escalation_reduces_the_response_time_limit_by_33_percent(self):
        ticket = escalated_ticket()
        # 4h * 0.67 = 2h40m48s, counted from the escalation
        assert ticket.response_time_limit == timedelta(hours=2, minutes=40, seconds=48)
        assert ticket.response_deadline == T0 + timedelta(hours=5) + ticket.response_time_limit


class TestReassignment:
    def test_due_when_agent_did_not_open_within_half_of_the_limit(self):
        ticket = escalated_ticket()
        half = ticket.response_time_limit / 2  # 1h20m24s
        escalated_at = T0 + timedelta(hours=5)
        assert not ticket.is_reassignment_due(escalated_at + half - timedelta(seconds=1))
        assert ticket.is_reassignment_due(escalated_at + half)

    def test_not_due_once_the_agent_opened_the_ticket(self):
        ticket = escalated_ticket()
        ticket.mark_opened_by(AGENT, T0 + timedelta(hours=5, minutes=10))
        assert not ticket.is_reassignment_due(T0 + timedelta(days=1))

    def test_opening_by_someone_else_does_not_count(self):
        ticket = escalated_ticket()
        ticket.mark_opened_by(MANAGER, T0 + timedelta(hours=5, minutes=10))
        assert ticket.is_reassignment_due(T0 + timedelta(hours=7))

    def test_reassigning_to_a_different_agent(self):
        ticket = escalated_ticket()
        now = T0 + timedelta(hours=7)
        ticket.reassign(Assignment(OTHER_AGENT, MANAGER), now)

        assert ticket.agent_id == OTHER_AGENT
        assert ticket.assigned_at == now
        # The new agent gets a fresh window to open the ticket.
        assert not ticket.is_reassignment_due(now + timedelta(minutes=1))

    def test_cannot_reassign_to_the_same_agent(self):
        with pytest.raises(ReassignmentNotAllowed):
            escalated_ticket().reassign(Assignment(AGENT, MANAGER), T0 + timedelta(hours=7))

    def test_cannot_reassign_before_due(self):
        with pytest.raises(ReassignmentNotAllowed):
            escalated_ticket().reassign(Assignment(OTHER_AGENT, MANAGER), T0 + timedelta(hours=5, minutes=1))

    def test_non_escalated_tickets_are_never_reassigned(self):
        assert not open_ticket().is_reassignment_due(T0 + timedelta(days=30))


class TestAutomaticClosing:
    def test_closed_when_the_customer_does_not_reply_within_seven_days(self):
        ticket = open_ticket()
        asked_at = T0 + timedelta(hours=1)
        ticket.post_message(AGENT, "Can you send a screenshot?", asked_at)

        assert not ticket.is_auto_close_due(asked_at + timedelta(days=7) - timedelta(seconds=1))
        ticket.close_for_inactivity(asked_at + timedelta(days=7))

        assert ticket.status is TicketStatus.CLOSED

    def test_a_customer_reply_cancels_it(self):
        ticket = open_ticket()
        ticket.post_message(AGENT, "Screenshot?", T0)
        ticket.post_message(CUSTOMER, "Here", T0 + timedelta(days=1))
        assert not ticket.is_auto_close_due(T0 + timedelta(days=30))

    def test_escalated_tickets_are_never_closed_automatically(self):
        ticket = escalated_ticket()
        ticket.post_message(AGENT, "Screenshot?", T0 + timedelta(hours=6))
        with pytest.raises(InvalidTicketState):
            ticket.close_for_inactivity(T0 + timedelta(days=30))


class TestClosing:
    @pytest.mark.parametrize("who", [CUSTOMER, AGENT, MANAGER])
    def test_open_ticket_closable_by_customer_agent_or_manager(self, who):
        ticket = open_ticket()
        ticket.close(who, T0)
        assert ticket.status is TicketStatus.CLOSED

    @pytest.mark.parametrize("who", [CUSTOMER, MANAGER])
    def test_escalated_ticket_closable_by_customer_or_manager(self, who):
        ticket = escalated_ticket()
        ticket.close(who, T0 + timedelta(hours=6))
        assert ticket.status is TicketStatus.CLOSED

    def test_escalated_ticket_not_closable_by_the_agent(self):
        ticket = escalated_ticket()
        assert not ticket.can_close(AGENT)
        with pytest.raises(ActionNotAllowed):
            ticket.close(AGENT, T0 + timedelta(hours=6))

    def test_strangers_cannot_close(self):
        with pytest.raises(ActionNotAllowed):
            open_ticket().close(STRANGER, T0)


class TestReopening:
    def test_customer_reopens_within_seven_days(self):
        ticket = open_ticket()
        ticket.close(AGENT, T0)
        ticket.reopen(CUSTOMER, T0 + timedelta(days=7))
        assert ticket.status is TicketStatus.OPEN
        assert ticket.response_deadline == T0 + timedelta(days=7, hours=4)

    def test_not_after_seven_days(self):
        ticket = open_ticket()
        ticket.close(AGENT, T0)
        with pytest.raises(ReopenWindowExpired):
            ticket.reopen(CUSTOMER, T0 + timedelta(days=7, seconds=1))

    def test_only_the_customer_can_reopen(self):
        ticket = open_ticket()
        ticket.close(AGENT, T0)
        with pytest.raises(ActionNotAllowed):
            ticket.reopen(AGENT, T0 + timedelta(days=1))

    def test_an_open_ticket_cannot_be_reopened(self):
        with pytest.raises(InvalidTicketState):
            open_ticket().reopen(CUSTOMER, T0)

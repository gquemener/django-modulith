"""Django integration: persistence mapping, module wiring and HTTP endpoints."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.urls import reverse
from django.utils import timezone

from modules.accounts.models import User
from modules.support_team.models import Agent
from modules.ticketing.bootstrap import ticketing_service
from modules.ticketing.domain import ConcurrencyConflict, Priority, TicketStatus
from modules.ticketing.infrastructure.repository import DjangoTicketRepository
from modules.ticketing.infrastructure.sql import execute, fetch_all, from_db_uuid, to_db_datetime, to_db_uuid

pytestmark = pytest.mark.django_db


def ticket_row(ticket_id):
    [row] = fetch_all("SELECT * FROM ticketing_ticket WHERE id = %s", [to_db_uuid(ticket_id)])
    return row


@pytest.fixture
def team():
    maria = Agent.objects.create(user=User.objects.create_user("maria", password="pw"), role=Agent.Role.MANAGER)
    alice = Agent.objects.create(user=User.objects.create_user("alice", password="pw"), manager=maria)
    customer = User.objects.create_user("carol", password="pw")
    return {"manager": maria.user, "agent": alice.user, "customer": customer}


def test_repository_round_trip(team):
    service = ticketing_service()
    ticket_id = service.open_ticket(team["customer"].pk, "Bug", "It crashes", Priority.HIGH)
    service.post_message(ticket_id, team["agent"].pk, "Which version?")
    service.post_message(ticket_id, team["customer"].pk, "2.1")

    ticket = DjangoTicketRepository().get(ticket_id)

    assert ticket.agent_id == team["agent"].pk
    assert ticket.manager_id == team["manager"].pk
    assert [m.body for m in ticket.messages] == ["It crashes", "Which version?", "2.1"]
    assert ticket.version == 3


def test_repository_detects_concurrent_writes(team):
    ticket_id = ticketing_service().open_ticket(team["customer"].pk, "Bug", "x", Priority.LOW)
    repo = DjangoTicketRepository()
    first, second = repo.get(ticket_id), repo.get(ticket_id)
    first.post_message(team["agent"].pk, "A", timezone.now())
    second.post_message(team["agent"].pk, "B", timezone.now())

    repo.save(first)
    with pytest.raises(ConcurrencyConflict):
        repo.save(second)


def test_auto_close_policy_end_to_end(team):
    service = ticketing_service()
    ticket_id = service.open_ticket(team["customer"].pk, "Bug", "x", Priority.LOW)
    service.post_message(ticket_id, team["agent"].pk, "Screenshot?")

    later = timezone.now() + timedelta(days=8)
    with patch("modules.ticketing.infrastructure.adapters.timezone.now", return_value=later):
        report = ticketing_service().run_policies()

    assert report.closed == [ticket_id]
    assert ticket_row(ticket_id)["status"] == TicketStatus.CLOSED


def test_customer_journey_over_http(client, team):
    client.force_login(team["customer"])
    response = client.post(reverse("ticketing:open"), {
        "title": "Printer on fire", "priority": "urgent", "description": "Help!",
    })
    [row] = fetch_all("SELECT id FROM ticketing_ticket")
    ticket_id = from_db_uuid(row["id"])
    assert response.url == reverse("ticketing:detail", args=[ticket_id])

    page = client.get(response.url)
    assert b"Printer on fire" in page.content
    assert b"Escalate" not in page.content  # still within the SLA

    client.post(reverse("ticketing:close", args=[ticket_id]))
    assert ticket_row(ticket_id)["status"] == "closed"


def test_agent_cannot_close_an_escalated_ticket_over_http(client, team):
    service = ticketing_service()
    ticket_id = service.open_ticket(team["customer"].pk, "Bug", "x", Priority.URGENT)
    two_hours_ago = to_db_datetime(timezone.now() - timedelta(hours=2))
    execute(
        "UPDATE ticketing_ticket SET awaiting_agent_since = %s, assigned_at = %s WHERE id = %s",
        [two_hours_ago, two_hours_ago, to_db_uuid(ticket_id)],
    )
    service.escalate(ticket_id, team["customer"].pk)

    client.force_login(team["agent"])
    client.post(reverse("ticketing:close", args=[ticket_id]), follow=True)

    row = ticket_row(ticket_id)
    assert row["status"] == "open"
    # Opening the page marked the escalated ticket as opened by its agent.
    assert row["opened_by_agent_since_escalation"]


def test_tickets_are_private(client, team):
    ticket_id = ticketing_service().open_ticket(team["customer"].pk, "Bug", "x", Priority.LOW)
    client.force_login(User.objects.create_user("eve", password="pw"))
    assert client.get(reverse("ticketing:detail", args=[ticket_id])).status_code == 404

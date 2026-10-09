"""Read side: view models built for screens.

Lists read the persistence records directly (no need to load aggregates to
display a table). The detail view loads the aggregate so that what a viewer
is allowed to do is decided by the domain model itself.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.db.models import Q

from modules.accounts import api as accounts
from modules.support_team import api as support_team

from ..domain import AuthorRole, TicketNotFound, TicketStatus
from .models import TicketRecord
from .repository import DjangoTicketRepository


@dataclass(frozen=True)
class TicketRow:
    id: UUID
    title: str
    priority: str
    status: str
    is_escalated: bool
    waiting_for: str | None
    opened_at: datetime


@dataclass(frozen=True)
class MessageView:
    author_name: str
    author_role: str
    body: str
    sent_at: datetime


@dataclass(frozen=True)
class TicketDetails:
    id: UUID
    title: str
    priority: str
    status: str
    viewer_role: str
    customer_name: str
    agent_name: str
    manager_name: str | None
    opened_at: datetime
    closed_at: datetime | None
    escalated_at: datetime | None
    response_deadline: datetime | None
    reassignment_deadline: datetime | None
    auto_close_at: datetime | None
    reopen_deadline: datetime | None
    messages: list[MessageView]
    can_post: bool
    can_escalate: bool
    can_close: bool
    can_reopen: bool


def _rows(queryset) -> list[TicketRow]:
    return [
        TicketRow(
            id=r.id,
            title=r.title,
            priority=r.priority,
            status=r.status,
            is_escalated=r.escalated_at is not None and r.status == TicketStatus.OPEN,
            waiting_for=(
                None if r.status != TicketStatus.OPEN
                else "agent" if r.awaiting_agent_since
                else "customer" if r.awaiting_customer_since
                else None
            ),
            opened_at=r.opened_at,
        )
        for r in queryset
    ]


def customer_tickets(customer_id: UUID) -> list[TicketRow]:
    return _rows(TicketRecord.objects.filter(customer_id=customer_id).order_by("status", "-opened_at"))


def staff_inbox(staff_id: UUID) -> dict[str, list[TicketRow]]:
    open_tickets = TicketRecord.objects.filter(status=TicketStatus.OPEN)
    return {
        "assigned": _rows(open_tickets.filter(agent_id=staff_id).order_by("awaiting_agent_since")),
        "escalated_to_me": _rows(
            open_tickets.filter(manager_id=staff_id, escalated_at__isnull=False).order_by("escalated_at")
        ),
        "closed": _rows(
            TicketRecord.objects.filter(Q(agent_id=staff_id) | Q(manager_id=staff_id), status=TicketStatus.CLOSED)
            .order_by("-closed_at")[:20]
        ),
    }


def ticket_details(ticket_id: UUID, viewer_id: UUID, now: datetime) -> TicketDetails:
    """Raise TicketNotFound if the ticket doesn't exist or the viewer may not see it."""
    ticket = DjangoTicketRepository().get(ticket_id)
    if viewer_id == ticket.customer_id:
        role = "customer"
    elif viewer_id == ticket.agent_id:
        role = "agent"
    elif viewer_id == ticket.manager_id:
        role = "manager"
    else:
        raise TicketNotFound(f"Ticket {ticket_id} not found.")

    names = accounts.display_names(
        {ticket.customer_id, ticket.agent_id, *([ticket.manager_id] if ticket.manager_id else []),
         *(m.author_id for m in ticket.messages)}
    )
    unknown = "Former team member"
    return TicketDetails(
        id=ticket.id,
        title=ticket.title,
        priority=ticket.priority.value,
        status=ticket.status.value,
        viewer_role=role,
        customer_name=names.get(ticket.customer_id, "Customer"),
        agent_name=names.get(ticket.agent_id, unknown),
        manager_name=names.get(ticket.manager_id) if ticket.manager_id else None,
        opened_at=ticket.opened_at,
        closed_at=ticket.closed_at,
        escalated_at=ticket.escalated_at,
        response_deadline=ticket.response_deadline,
        reassignment_deadline=ticket.reassignment_deadline,
        auto_close_at=ticket.auto_close_at,
        reopen_deadline=ticket.reopen_deadline,
        messages=[
            MessageView(
                author_name=names.get(m.author_id, "Customer" if m.author_role is AuthorRole.CUSTOMER else unknown),
                author_role=m.author_role.value,
                body=m.body,
                sent_at=m.sent_at,
            )
            for m in ticket.messages
        ],
        can_post=ticket.is_open and role in ("customer", "agent"),
        can_escalate=ticket.can_escalate(viewer_id, now),
        can_close=ticket.can_close(viewer_id),
        can_reopen=ticket.can_reopen(viewer_id, now),
    )


def is_support_staff(user_id: UUID) -> bool:
    return support_team.is_support_staff(user_id)

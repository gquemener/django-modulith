import uuid
from datetime import datetime

from django.db.models import F

from ..domain import (
    AgentId,
    Assignment,
    AuthorRole,
    ConcurrencyConflict,
    CustomerId,
    Message,
    Priority,
    Ticket,
    TicketId,
    TicketNotFound,
    TicketRepository,
    TicketStatus,
)
from .models import MessageRecord, TicketRecord


class DjangoTicketRepository(TicketRepository):
    """Maps the Ticket aggregate to/from relational records (Data Mapper)."""

    def next_identity(self) -> TicketId:
        return TicketId(uuid.uuid4())

    def get(self, ticket_id: TicketId) -> Ticket:
        try:
            record = TicketRecord.objects.prefetch_related("messages").get(pk=ticket_id)
        except TicketRecord.DoesNotExist:
            raise TicketNotFound(f"Ticket {ticket_id} not found.") from None
        return self._to_domain(record)

    def save(self, ticket: Ticket) -> None:
        fields = self._to_fields(ticket)
        if ticket.version == 0:
            TicketRecord.objects.create(id=ticket.id, version=1, **fields)
        else:
            updated = TicketRecord.objects.filter(pk=ticket.id, version=ticket.version).update(
                version=F("version") + 1, **fields
            )
            if not updated:
                raise ConcurrencyConflict(f"Ticket {ticket.id} was modified concurrently.")
        self._insert_new_messages(ticket)
        ticket.version += 1

    def ids_awaiting_customer_since(self, before: datetime) -> list[TicketId]:
        return list(
            TicketRecord.objects.filter(
                status=TicketStatus.OPEN,
                escalated_at__isnull=True,
                awaiting_customer_since__lte=before,
            ).values_list("id", flat=True)
        )

    def ids_of_escalated_unopened(self) -> list[TicketId]:
        return list(
            TicketRecord.objects.filter(
                status=TicketStatus.OPEN,
                escalated_at__isnull=False,
                opened_by_agent_since_escalation=False,
            ).values_list("id", flat=True)
        )

    # Messages are immutable and append-only: only new ones are inserted.
    def _insert_new_messages(self, ticket: Ticket) -> None:
        known = set(MessageRecord.objects.filter(ticket_id=ticket.id).values_list("id", flat=True))
        MessageRecord.objects.bulk_create([
            MessageRecord(
                id=message.id,
                ticket_id=ticket.id,
                position=position,
                author_role=message.author_role,
                author_id=message.author_id,
                body=message.body,
                sent_at=message.sent_at,
            )
            for position, message in enumerate(ticket.messages)
            if message.id not in known
        ])

    @staticmethod
    def _to_fields(ticket: Ticket) -> dict:
        return {
            "customer_id": ticket.customer_id,
            "agent_id": ticket.agent_id,
            "manager_id": ticket.manager_id,
            "title": ticket.title,
            "priority": ticket.priority.value,
            "status": ticket.status.value,
            "opened_at": ticket.opened_at,
            "assigned_at": ticket.assigned_at,
            "awaiting_agent_since": ticket.awaiting_agent_since,
            "awaiting_customer_since": ticket.awaiting_customer_since,
            "escalated_at": ticket.escalated_at,
            "opened_by_agent_since_escalation": ticket.opened_by_agent_since_escalation,
            "closed_at": ticket.closed_at,
        }

    @staticmethod
    def _to_domain(record: TicketRecord) -> Ticket:
        return Ticket(
            id=TicketId(record.id),
            customer_id=CustomerId(record.customer_id),
            title=record.title,
            priority=Priority(record.priority),
            assignment=Assignment(agent_id=AgentId(record.agent_id), manager_id=record.manager_id),
            assigned_at=record.assigned_at,
            opened_at=record.opened_at,
            status=TicketStatus(record.status),
            messages=[
                Message(
                    id=m.id,
                    author_role=AuthorRole(m.author_role),
                    author_id=m.author_id,
                    body=m.body,
                    sent_at=m.sent_at,
                )
                for m in record.messages.all()
            ],
            awaiting_agent_since=record.awaiting_agent_since,
            awaiting_customer_since=record.awaiting_customer_since,
            escalated_at=record.escalated_at,
            opened_by_agent_since_escalation=record.opened_by_agent_since_escalation,
            closed_at=record.closed_at,
            version=record.version,
        )

"""Persistence models.

These are *not* the domain model: they are plain data records mapped to and
from the Ticket aggregate by `DjangoTicketRepository`. No business logic here.
"""

from django.db import models

from ..domain import AuthorRole, Priority, TicketStatus


def _choices(enum):
    return [(member.value, member.name.title()) for member in enum]


class TicketRecord(models.Model):
    id = models.UUIDField(primary_key=True)
    version = models.PositiveIntegerField()
    customer_id = models.UUIDField(db_index=True)
    agent_id = models.UUIDField(db_index=True)
    manager_id = models.UUIDField(null=True, db_index=True)
    title = models.CharField(max_length=200)
    priority = models.CharField(max_length=16, choices=_choices(Priority))
    status = models.CharField(max_length=16, choices=_choices(TicketStatus))
    opened_at = models.DateTimeField()
    assigned_at = models.DateTimeField()
    awaiting_agent_since = models.DateTimeField(null=True)
    awaiting_customer_since = models.DateTimeField(null=True)
    escalated_at = models.DateTimeField(null=True)
    opened_by_agent_since_escalation = models.BooleanField(default=False)
    closed_at = models.DateTimeField(null=True)

    class Meta:
        db_table = "ticketing_ticket"
        indexes = [models.Index(fields=["status", "awaiting_customer_since"])]


class MessageRecord(models.Model):
    id = models.UUIDField(primary_key=True)
    ticket = models.ForeignKey(TicketRecord, on_delete=models.CASCADE, related_name="messages")
    position = models.PositiveIntegerField()
    author_role = models.CharField(max_length=16, choices=_choices(AuthorRole))
    author_id = models.UUIDField()
    body = models.TextField()
    sent_at = models.DateTimeField()

    class Meta:
        db_table = "ticketing_message"
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(fields=["ticket", "position"], name="unique_message_position"),
        ]

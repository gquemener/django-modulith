import uuid
from datetime import datetime

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
from .sql import (
    execute,
    execute_many,
    fetch_all,
    fetch_one,
    from_db_datetime,
    from_db_uuid,
    to_db_datetime,
    to_db_uuid,
)

_TICKET_COLUMNS = (
    "customer_id",
    "agent_id",
    "manager_id",
    "title",
    "priority",
    "status",
    "opened_at",
    "assigned_at",
    "awaiting_agent_since",
    "awaiting_customer_since",
    "escalated_at",
    "opened_by_agent_since_escalation",
    "closed_at",
)


class DjangoTicketRepository(TicketRepository):
    """Maps the Ticket aggregate to/from relational rows with plain SQL (Data Mapper)."""

    def next_identity(self) -> TicketId:
        return TicketId(uuid.uuid4())

    def get(self, ticket_id: TicketId) -> Ticket:
        row = fetch_one(
            f"SELECT id, version, {', '.join(_TICKET_COLUMNS)} FROM ticketing_ticket WHERE id = %s",
            [to_db_uuid(ticket_id)],
        )
        if row is None:
            raise TicketNotFound(f"Ticket {ticket_id} not found.")
        messages = fetch_all(
            "SELECT id, author_role, author_id, body, sent_at FROM ticketing_message"
            " WHERE ticket_id = %s ORDER BY position",
            [to_db_uuid(ticket_id)],
        )
        return self._to_domain(row, messages)

    def save(self, ticket: Ticket) -> None:
        values = self._to_row(ticket)
        if ticket.version == 0:
            execute(
                f"INSERT INTO ticketing_ticket (id, version, {', '.join(_TICKET_COLUMNS)})"
                f" VALUES (%s, 1, {', '.join(['%s'] * len(_TICKET_COLUMNS))})",
                [to_db_uuid(ticket.id), *values],
            )
        else:
            updated = execute(
                f"UPDATE ticketing_ticket SET version = version + 1,"
                f" {', '.join(f'{column} = %s' for column in _TICKET_COLUMNS)}"
                " WHERE id = %s AND version = %s",
                [*values, to_db_uuid(ticket.id), ticket.version],
            )
            if not updated:
                raise ConcurrencyConflict(f"Ticket {ticket.id} was modified concurrently.")
        self._insert_new_messages(ticket)
        ticket.version += 1

    def ids_awaiting_customer_since(self, before: datetime) -> list[TicketId]:
        rows = fetch_all(
            "SELECT id FROM ticketing_ticket"
            " WHERE status = %s AND escalated_at IS NULL AND awaiting_customer_since <= %s",
            [TicketStatus.OPEN.value, to_db_datetime(before)],
        )
        return [TicketId(from_db_uuid(row["id"])) for row in rows]

    def ids_of_escalated_unopened(self) -> list[TicketId]:
        rows = fetch_all(
            "SELECT id FROM ticketing_ticket"
            " WHERE status = %s AND escalated_at IS NOT NULL AND opened_by_agent_since_escalation = %s",
            [TicketStatus.OPEN.value, False],
        )
        return [TicketId(from_db_uuid(row["id"])) for row in rows]

    # Messages are immutable and append-only: only new ones are inserted.
    def _insert_new_messages(self, ticket: Ticket) -> None:
        known = {
            from_db_uuid(row["id"])
            for row in fetch_all("SELECT id FROM ticketing_message WHERE ticket_id = %s", [to_db_uuid(ticket.id)])
        }
        execute_many(
            "INSERT INTO ticketing_message (id, ticket_id, position, author_role, author_id, body, sent_at)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s)",
            [
                [
                    to_db_uuid(message.id),
                    to_db_uuid(ticket.id),
                    position,
                    message.author_role.value,
                    to_db_uuid(message.author_id),
                    message.body,
                    to_db_datetime(message.sent_at),
                ]
                for position, message in enumerate(ticket.messages)
                if message.id not in known
            ],
        )

    @staticmethod
    def _to_row(ticket: Ticket) -> list:
        """Values in the order of `_TICKET_COLUMNS`."""
        return [
            to_db_uuid(ticket.customer_id),
            to_db_uuid(ticket.agent_id),
            to_db_uuid(ticket.manager_id),
            ticket.title,
            ticket.priority.value,
            ticket.status.value,
            to_db_datetime(ticket.opened_at),
            to_db_datetime(ticket.assigned_at),
            to_db_datetime(ticket.awaiting_agent_since),
            to_db_datetime(ticket.awaiting_customer_since),
            to_db_datetime(ticket.escalated_at),
            ticket.opened_by_agent_since_escalation,
            to_db_datetime(ticket.closed_at),
        ]

    @staticmethod
    def _to_domain(row: dict, messages: list[dict]) -> Ticket:
        return Ticket(
            id=TicketId(from_db_uuid(row["id"])),
            customer_id=CustomerId(from_db_uuid(row["customer_id"])),
            title=row["title"],
            priority=Priority(row["priority"]),
            assignment=Assignment(
                agent_id=AgentId(from_db_uuid(row["agent_id"])),
                manager_id=from_db_uuid(row["manager_id"]),
            ),
            assigned_at=from_db_datetime(row["assigned_at"]),
            opened_at=from_db_datetime(row["opened_at"]),
            status=TicketStatus(row["status"]),
            messages=[
                Message(
                    id=from_db_uuid(m["id"]),
                    author_role=AuthorRole(m["author_role"]),
                    author_id=from_db_uuid(m["author_id"]),
                    body=m["body"],
                    sent_at=from_db_datetime(m["sent_at"]),
                )
                for m in messages
            ],
            awaiting_agent_since=from_db_datetime(row["awaiting_agent_since"]),
            awaiting_customer_since=from_db_datetime(row["awaiting_customer_since"]),
            escalated_at=from_db_datetime(row["escalated_at"]),
            opened_by_agent_since_escalation=bool(row["opened_by_agent_since_escalation"]),
            closed_at=from_db_datetime(row["closed_at"]),
            version=row["version"],
        )

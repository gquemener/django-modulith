"""Ticketing tables, defined in plain SQL: the module has no Django model.

`DjangoTicketRepository` and the read-side queries map these tables by hand.
UUIDs are stored as 32-char hex strings and datetimes as naive UTC text.
"""

from django.db import migrations

SCHEMA = """
CREATE TABLE "ticketing_ticket" (
    "id" char(32) NOT NULL PRIMARY KEY,
    "version" integer NOT NULL CHECK ("version" >= 0),
    "customer_id" char(32) NOT NULL,
    "agent_id" char(32) NOT NULL,
    "manager_id" char(32) NULL,
    "title" varchar(200) NOT NULL,
    "priority" varchar(16) NOT NULL,
    "status" varchar(16) NOT NULL,
    "opened_at" datetime NOT NULL,
    "assigned_at" datetime NOT NULL,
    "awaiting_agent_since" datetime NULL,
    "awaiting_customer_since" datetime NULL,
    "escalated_at" datetime NULL,
    "opened_by_agent_since_escalation" bool NOT NULL,
    "closed_at" datetime NULL
);
CREATE INDEX "ticketing_ticket_customer_id" ON "ticketing_ticket" ("customer_id");
CREATE INDEX "ticketing_ticket_agent_id" ON "ticketing_ticket" ("agent_id");
CREATE INDEX "ticketing_ticket_manager_id" ON "ticketing_ticket" ("manager_id");
CREATE INDEX "ticketing_ticket_status_awaiting_customer" ON "ticketing_ticket" ("status", "awaiting_customer_since");

CREATE TABLE "ticketing_message" (
    "id" char(32) NOT NULL PRIMARY KEY,
    "ticket_id" char(32) NOT NULL REFERENCES "ticketing_ticket" ("id") ON DELETE CASCADE,
    "position" integer NOT NULL CHECK ("position" >= 0),
    "author_role" varchar(16) NOT NULL,
    "author_id" char(32) NOT NULL,
    "body" text NOT NULL,
    "sent_at" datetime NOT NULL,
    CONSTRAINT "unique_message_position" UNIQUE ("ticket_id", "position")
);
"""

DROP_SCHEMA = """
DROP TABLE "ticketing_message";
DROP TABLE "ticketing_ticket";
"""


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.RunSQL(SCHEMA, DROP_SCHEMA),
    ]

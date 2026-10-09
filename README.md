# Helpdesk — a Django modular monolith

```sh
uv sync
uv run python manage.py migrate
uv run python manage.py seed_demo          # users: maria (manager), alice, bob (agents), carol, dave (customers) — password "demo"
uv run python manage.py runserver           # http://127.0.0.1:8888 (override with DJANGO_PORT=xxxx)
uv run python manage.py run_ticket_policies  # schedule every minute (cron/systemd timer): auto-close & auto-reassign

uv run pytest          # tests
uv run lint-imports    # architecture rules
```

## Modules

| Module | Responsibility | Style |
|---|---|---|
| `accounts` | Users (UUID identities) | Django Active Record |
| `support_team` | Agents, managers, availability | Django Active Record |
| `ticketing` | Support ticket lifecycle | **Domain Model** (layered) |

Modules only talk to each other through their `api.py` (plain DTOs, never models) and refer to each
other's entities by UUID, without cross-module foreign keys. `import-linter` enforces these rules (see `pyproject.toml`).

## Ticketing layers

```
presentation/    views, forms, templates      → calls application, reads via infrastructure.queries
infrastructure/  plain SQL access, repository (Data Mapper), adapters, read-side queries
application/     TicketingService (one use case = one transaction), ports (Clock, AgentDirectory…)
domain/          Ticket aggregate, SLA rules, events, exceptions, repository interface — pure Python
bootstrap.py     composition root
```

- The `Ticket` aggregate holds **every** business rule. Time is passed in as `now`, so the rules are deterministic and
  tested without a database (`tests/test_domain.py`).
- Ticketing has no Django model: its tables are created by a `RunSQL` migration, and `DjangoTicketRepository` hydrates
  the aggregate from plain SQL. It uses optimistic locking (`version`) and inserts messages append-only.
- The aggregate records domain events, which are published after commit. For now they are only logged.
  An outbox or bus can be plugged in behind `EventPublisher`.

## Interpretation of the requirements

- SLA by priority: low 24h, medium 8h, high 4h, urgent 1h (`domain/sla.py`). The clock starts at the first unanswered
  customer message, and any agent message counts as the agent's response.
- Escalation is possible once the response deadline has passed. The agent then gets a fresh window of 67% of the limit,
  counted from the escalation.
- "Opening" an escalated ticket means the assigned agent views its page. Otherwise, after 50% of the reduced limit,
  the ticket is reassigned to another available agent, who gets a new window of their own.
- Any agent message awaiting a reply counts as "a question": with no customer reply for 7 days, the ticket closes,
  unless it is escalated.
- A customer may close at any time. The agent may close unless the ticket is escalated. The agent's manager may always close.
- Reopening (by the customer, within 7 days) starts a fresh cycle and clears the escalation.

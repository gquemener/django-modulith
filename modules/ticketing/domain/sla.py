"""Service level agreement: how long an agent has to answer, per priority."""

from datetime import timedelta
from enum import StrEnum


class Priority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


RESPONSE_TIME_LIMITS: dict[Priority, timedelta] = {
    Priority.LOW: timedelta(hours=24),
    Priority.MEDIUM: timedelta(hours=8),
    Priority.HIGH: timedelta(hours=4),
    Priority.URGENT: timedelta(hours=1),
}

# Escalation reduces the agent's response time limit by 33%.
ESCALATION_REDUCTION = 0.33
# An escalated ticket not opened within 50% of the response time limit is reassigned.
REASSIGNMENT_RATIO = 0.5
# Tickets awaiting the customer's reply are closed after seven days.
AUTO_CLOSE_AFTER = timedelta(days=7)
# A customer can reopen a ticket closed in the past seven days.
REOPEN_WINDOW = timedelta(days=7)


def response_time_limit(priority: Priority, *, escalated: bool) -> timedelta:
    limit = RESPONSE_TIME_LIMITS[priority]
    return limit * (1 - ESCALATION_REDUCTION) if escalated else limit

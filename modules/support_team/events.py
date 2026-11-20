"""Integration events published by the support_team module.

Other modules subscribe through `modules.support_team.api`. Events are
delivered in-process, once the transaction that produced them commits, so
subscribers never react to something that was rolled back. A failing
subscriber is logged and does not prevent the others from running.
"""

import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from django.db import transaction

logger = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class AgentSuspended:
    agent_id: UUID
    occurred_at: datetime


_subscribers: defaultdict[type, list[Callable[[Any], None]]] = defaultdict(list)


def subscribe(event_type: type, handler: Callable[[Any], None]) -> None:
    if handler not in _subscribers[event_type]:
        _subscribers[event_type].append(handler)


def publish(event: object) -> None:
    transaction.on_commit(lambda: _deliver(event))


def _deliver(event: object) -> None:
    for handler in list(_subscribers[type(event)]):
        try:
            handler(event)
        except Exception:
            logger.exception("Subscriber %r failed on %r", handler, event)

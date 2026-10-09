"""Interfaces the application layer needs from the outside world."""

from collections.abc import Collection
from contextlib import AbstractContextManager
from datetime import datetime
from typing import Protocol
from uuid import UUID

from ..domain import Assignment
from ..domain.events import DomainEvent


class Clock(Protocol):
    def now(self) -> datetime: ...


class AgentDirectory(Protocol):
    """Who can handle tickets, and who manages them (backed by support_team)."""

    def assign_agent(self, exclude: Collection[UUID] = ()) -> Assignment | None: ...

    def is_support_staff(self, user_id: UUID) -> bool: ...


class EventPublisher(Protocol):
    def publish(self, events: list[DomainEvent]) -> None: ...


class TransactionManager(Protocol):
    def atomic(self) -> AbstractContextManager: ...

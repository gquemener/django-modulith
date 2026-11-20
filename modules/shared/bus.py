"""In-process event bus shared by all modules.

A handler is any callable taking one event. The event type(s) it handles are
read from the type hint of that parameter, so there is no mapping to maintain:

    class NotifyAgent:
        def __call__(self, event: TicketOpened) -> None: ...

    def audit(event: TicketOpened | TicketClosed) -> None: ...

Events are delivered once the current transaction commits, so handlers never
react to something that was rolled back. A failing handler is logged and does
not prevent the others from running. Handlers also receive subclasses of the
type they declare.
"""

import inspect
import logging
import types
import typing
from collections import defaultdict
from collections.abc import Callable, Iterable
from typing import Any

from django.db import transaction

logger = logging.getLogger(__name__)

Handler = Callable[[Any], None]


class InvalidHandler(TypeError):
    pass


def event_types_of(handler: Handler) -> tuple[type, ...]:
    """The event classes a handler declares through the type hint of its parameter."""
    function = handler if inspect.isfunction(handler) or inspect.ismethod(handler) else getattr(handler, "__call__")
    parameters = list(inspect.signature(function).parameters.values())
    if len(parameters) != 1:
        raise InvalidHandler(f"{handler!r} must take exactly one parameter: the event.")
    hint = typing.get_type_hints(function).get(parameters[0].name)
    if hint is None:
        raise InvalidHandler(f"{handler!r} must annotate its event parameter with the event type(s) it handles.")
    event_types = typing.get_args(hint) if typing.get_origin(hint) in (typing.Union, types.UnionType) else (hint,)
    if not all(isinstance(t, type) for t in event_types):
        raise InvalidHandler(f"{handler!r} must annotate its event parameter with event classes, got {hint!r}.")
    return event_types


class EventBus:
    def __init__(self, defer: Callable[[Callable[[], None]], None] = transaction.on_commit) -> None:
        self._defer = defer
        self._handlers: defaultdict[type, list[Handler]] = defaultdict(list)

    def subscribe(self, handler: Handler) -> None:
        for event_type in event_types_of(handler):
            self._handlers[event_type].append(handler)

    def subscribe_all(self, handlers: Iterable[Handler]) -> None:
        for handler in handlers:
            self.subscribe(handler)

    def publish(self, event: object) -> None:
        self._defer(lambda: self._deliver(event))

    def handlers_of(self, event_type: type) -> list[Handler]:
        return [h for cls in event_type.__mro__ for h in self._handlers.get(cls, ())]

    def _deliver(self, event: object) -> None:
        logger.info("Event: %r", event)
        for handler in self.handlers_of(type(event)):
            try:
                handler(event)
            except Exception:
                logger.exception("Handler %r failed on %r", handler, event)


# The application-wide bus. Handlers are registered at startup (see apps.py).
bus = EventBus()

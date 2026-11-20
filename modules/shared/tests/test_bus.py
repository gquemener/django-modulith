"""The event bus, with deferred delivery under the test's control: no database."""

from dataclasses import dataclass

import pytest

from modules.shared.bus import EventBus, InvalidHandler, event_types_of


@dataclass(frozen=True)
class Opened:
    id: int


@dataclass(frozen=True)
class Closed:
    id: int


@dataclass(frozen=True)
class ClosedByCustomer(Closed):
    pass


class DeferredUntilCommit:
    def __init__(self):
        self.pending = []

    def __call__(self, callback):
        self.pending.append(callback)

    def commit(self):
        while self.pending:
            self.pending.pop(0)()


@pytest.fixture
def commit():
    return DeferredUntilCommit()


@pytest.fixture
def bus(commit):
    return EventBus(defer=commit)


class Recorder:
    def __init__(self):
        self.received = []

    def __call__(self, event: Opened) -> None:
        self.received.append(event)


def test_routes_events_on_the_handler_type_hint(bus, commit):
    on_opened = Recorder()
    closed = []

    def on_closed(event: Closed) -> None:
        closed.append(event)

    bus.subscribe_all([on_opened, on_closed])
    bus.publish(Opened(1))
    bus.publish(Closed(2))
    commit.commit()

    assert on_opened.received == [Opened(1)]
    assert closed == [Closed(2)]


def test_a_union_hint_subscribes_to_each_event(bus, commit):
    received = []

    def audit(event: Opened | Closed) -> None:
        received.append(event)

    bus.subscribe(audit)
    bus.publish(Opened(1))
    bus.publish(Closed(2))
    commit.commit()

    assert received == [Opened(1), Closed(2)]


def test_handlers_receive_subclasses_of_their_event(bus, commit):
    received = []

    def on_closed(event: Closed) -> None:
        received.append(event)

    bus.subscribe(on_closed)
    bus.publish(ClosedByCustomer(1))
    commit.commit()

    assert received == [ClosedByCustomer(1)]


def test_nothing_is_delivered_before_commit(bus, commit):
    handler = Recorder()
    bus.subscribe(handler)

    bus.publish(Opened(1))

    assert handler.received == []


def test_a_failing_handler_does_not_prevent_the_others(bus, commit):
    def failing(event: Opened) -> None:
        raise RuntimeError("boom")

    handler = Recorder()
    bus.subscribe_all([failing, handler])
    bus.publish(Opened(1))
    commit.commit()

    assert handler.received == [Opened(1)]


def test_events_published_by_a_handler_are_delivered_after_the_next_commit(bus, commit):
    closed = []

    def close_when_opened(event: Opened) -> None:
        bus.publish(Closed(event.id))

    def on_closed(event: Closed) -> None:
        closed.append(event)

    bus.subscribe_all([close_when_opened, on_closed])
    bus.publish(Opened(1))
    commit.commit()

    assert closed == [Closed(1)]


def test_handlers_must_declare_their_event_type():
    def untyped(event):
        pass

    with pytest.raises(InvalidHandler):
        event_types_of(untyped)


def test_handlers_must_take_a_single_event():
    def too_many(event: Opened, other: Closed) -> None:
        pass

    with pytest.raises(InvalidHandler):
        event_types_of(too_many)


def test_handlers_must_declare_classes():
    def not_a_class(event: "list[Opened]") -> None:
        pass

    with pytest.raises(InvalidHandler):
        event_types_of(not_a_class)

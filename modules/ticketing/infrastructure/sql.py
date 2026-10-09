"""Plain SQL access to the ticketing tables (see migrations/0001_initial.py).

Values are converted explicitly instead of relying on driver adapters:
UUIDs are stored as 32-char hex strings, datetimes as naive UTC text.
"""

from datetime import UTC, datetime
from uuid import UUID

from django.db import connection


def fetch_all(sql: str, params=()) -> list[dict]:
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def fetch_one(sql: str, params=()) -> dict | None:
    rows = fetch_all(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params=()) -> int:
    """Run a write statement and return the number of affected rows."""
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.rowcount


def execute_many(sql: str, params_list: list) -> None:
    if params_list:
        with connection.cursor() as cursor:
            cursor.executemany(sql, params_list)


def to_db_uuid(value: UUID | None) -> str | None:
    return None if value is None else value.hex


def from_db_uuid(value) -> UUID | None:
    return None if value is None else UUID(str(value))


def to_db_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).replace(tzinfo=None).isoformat(" ", timespec="microseconds")


def from_db_datetime(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value

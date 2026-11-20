"""Public API of the accounts module."""

from collections.abc import Collection
from uuid import UUID

from .models import User


def display_names(ids: Collection[UUID]) -> dict[UUID, str]:
    return {
        user.pk: user.get_full_name() or user.get_username()
        for user in User.objects.filter(pk__in=list(ids))
    }


def email_of(user_id: UUID) -> str | None:
    """The user's email address, or None if unknown."""
    email = User.objects.filter(pk=user_id).values_list("email", flat=True).first()
    return email or None

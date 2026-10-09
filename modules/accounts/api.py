"""Public API of the accounts module."""

from collections.abc import Collection
from uuid import UUID

from .models import User


def display_names(ids: Collection[UUID]) -> dict[UUID, str]:
    return {
        user.pk: user.get_full_name() or user.get_username()
        for user in User.objects.filter(pk__in=list(ids))
    }

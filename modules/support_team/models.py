"""Support team organisation.

This module is plain CRUD (who is an agent, who manages whom), so it happily
uses Django's Active Record models. It is private to the module: other modules
must go through `modules.support_team.api`.
"""

from django.conf import settings
from django.db import models


class Agent(models.Model):
    class Role(models.TextChoices):
        AGENT = "agent", "Agent"
        MANAGER = "manager", "Manager"

    # The agent identity is the user identity.
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        primary_key=True,
        on_delete=models.CASCADE,
        related_name="support_agent",
    )
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.AGENT)
    manager = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reports",
        limit_choices_to={"role": "manager"},
    )
    is_available = models.BooleanField(default=True)

    def __str__(self):
        return self.user.get_full_name() or self.user.get_username()

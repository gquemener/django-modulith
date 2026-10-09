import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Every person (customer, agent, manager) is a user identified by a UUID.

    The UUID is the identity other modules refer to (CustomerId, AgentId, ...),
    so no module needs a foreign key to this table.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

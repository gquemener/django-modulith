"""Integration events published by the support_team module.

They are part of its public API (re-exported by `api.py`): other modules
handle them by type-hinting a handler's parameter with them.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, kw_only=True)
class AgentSuspended:
    agent_id: UUID
    occurred_at: datetime

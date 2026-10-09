# Django discovers models in `<app>.models`; the real ones live in infrastructure.
from .infrastructure.models import MessageRecord, TicketRecord  # noqa: F401

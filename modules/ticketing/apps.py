from django.apps import AppConfig


class TicketingConfig(AppConfig):
    name = "modules.ticketing"
    label = "ticketing"
    verbose_name = "Ticketing"

    def ready(self) -> None:
        from .bootstrap import subscribe_to_other_modules

        subscribe_to_other_modules()

from importlib import import_module

from django.apps import AppConfig, apps
from django.utils.module_loading import module_has_submodule

from .bus import bus


class SharedConfig(AppConfig):
    name = "modules.shared"
    label = "shared"
    verbose_name = "Shared kernel"

    def ready(self) -> None:
        subscribe_event_handlers()


_subscribed = False


def subscribe_event_handlers() -> None:
    """Subscribe the handlers of every module exposing `bootstrap.event_handlers()`.

    Discovery is automatic, but each module still builds its handlers (and their
    dependencies) explicitly in its composition root.
    """
    global _subscribed
    if _subscribed:  # ready() may run more than once
        return
    for app_config in apps.get_app_configs():
        if not module_has_submodule(app_config.module, "bootstrap"):
            continue
        bootstrap = import_module(f"{app_config.name}.bootstrap")
        if hasattr(bootstrap, "event_handlers"):
            bus.subscribe_all(bootstrap.event_handlers())
    _subscribed = True

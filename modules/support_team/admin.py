from django.contrib import admin

from . import api
from .models import Agent


@admin.register(Agent)
class AgentAdmin(admin.ModelAdmin):
    list_display = ("__str__", "role", "manager", "is_available", "is_suspended")
    list_filter = ("role", "is_available", "is_suspended")
    readonly_fields = ("is_suspended",)  # changed through the "suspend" action, which notifies other modules
    actions = ["suspend"]

    @admin.action(description="Suspend selected agents")
    def suspend(self, request, queryset):
        for agent_id in queryset.values_list("pk", flat=True):
            api.suspend_agent(agent_id)

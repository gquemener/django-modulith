from django.contrib import admin

from .models import Agent


@admin.register(Agent)
class AgentAdmin(admin.ModelAdmin):
    list_display = ("__str__", "role", "manager", "is_available")
    list_filter = ("role", "is_available")

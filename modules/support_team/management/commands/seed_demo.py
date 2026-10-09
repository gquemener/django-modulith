from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from modules.support_team.models import Agent

PASSWORD = "demo"


class Command(BaseCommand):
    help = "Create demo users: a manager, two agents and two customers (password: demo)."

    def handle(self, *args, **options):
        User = get_user_model()

        def user(username, first_name, **extra):
            obj, created = User.objects.get_or_create(
                username=username, defaults={"first_name": first_name, **extra}
            )
            if created:
                obj.set_password(PASSWORD)
                obj.save()
            return obj

        user("admin", "Admin", is_staff=True, is_superuser=True)
        maria = user("maria", "Maria (manager)")
        manager, _ = Agent.objects.get_or_create(
            user=maria, defaults={"role": Agent.Role.MANAGER}
        )
        for username, name in [("alice", "Alice (agent)"), ("bob", "Bob (agent)")]:
            Agent.objects.get_or_create(
                user=user(username, name),
                defaults={"role": Agent.Role.AGENT, "manager": manager},
            )
        user("carol", "Carol (customer)")
        user("dave", "Dave (customer)")

        self.stdout.write(self.style.SUCCESS(
            "Demo users: admin, maria, alice, bob, carol, dave — password: demo"
        ))

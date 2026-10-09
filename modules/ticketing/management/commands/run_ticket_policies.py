from django.core.management.base import BaseCommand

from modules.ticketing.bootstrap import ticketing_service


class Command(BaseCommand):
    help = "Apply time-based ticket rules (auto-close, auto-reassign). Run it every minute from cron."

    def handle(self, *args, **options):
        report = ticketing_service().run_policies()
        self.stdout.write(
            f"Closed {len(report.closed)} ticket(s), reassigned {len(report.reassigned)} ticket(s)."
        )

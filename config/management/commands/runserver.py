import os

from django.contrib.staticfiles.management.commands.runserver import Command as RunserverCommand


class Command(RunserverCommand):
    # Port 8000 is often taken; override with DJANGO_PORT or `runserver <port>`.
    default_port = os.environ.get("DJANGO_PORT", "8888")

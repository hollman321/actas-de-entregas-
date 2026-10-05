import secrets
import string

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from accounts.models import UserRole


class Command(BaseCommand):
    help = "Crea tres cuentas piloto con roles Técnico, Supervisor uno y Supervisor dos."

    def add_arguments(self, parser):
        parser.add_argument("--technician-email", required=True)
        parser.add_argument("--supervisor-one-email", required=True)
        parser.add_argument("--supervisor-two-email", required=True)

    def handle(self, *args, **options):
        users = get_user_model()
        alphabet = string.ascii_letters + string.digits + "!@#$%_-"
        pilots = [
            ("pilot_technician", "TECHNICIAN", options["technician_email"]),
            ("pilot_supervisor_one", "SUPERVISOR_ONE", options["supervisor_one_email"]),
            ("pilot_supervisor_two", "SUPERVISOR_TWO", options["supervisor_two_email"]),
        ]
        existing = [username for username, _, _ in pilots if users.objects.filter(username=username).exists()]
        if existing:
            raise CommandError(f"Ya existen estos usuarios piloto: {', '.join(existing)}; no se modificó ninguna cuenta.")
        for username, role, email in pilots:
            password = "".join(secrets.choice(alphabet) for _ in range(20))
            user = users.objects.create_user(username=username, email=email, password=password)
            UserRole.objects.create(user=user, role=role, active=True)
            self.stdout.write(self.style.SUCCESS(f"{role}: usuario={username}, clave temporal={password}"))
        self.stdout.write("Entrega las claves por un canal seguro y solicita que las cambien al iniciar el piloto.")

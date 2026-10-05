from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from actas.models import CampaignCatalog


TEST_CAMPAIGNS = (
    "Campaña de prueba - Operaciones",
    "Campaña de prueba - Tecnología",
    "Campaña de prueba - Servicio",
)


class Command(BaseCommand):
    help = "Crea campañas ficticias de ejemplo, solo en ambientes de prueba."

    def handle(self, *args, **options):
        if settings.APP_ENV not in {"test", "testing", "staging"}:
            raise CommandError(
                "Este comando solo funciona con APP_ENV=test/testing/staging."
            )

        for name in TEST_CAMPAIGNS:
            CampaignCatalog.objects.update_or_create(
                name=name,
                defaults={"active": True},
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"{len(TEST_CAMPAIGNS)} campañas ficticias de prueba disponibles."
            )
        )

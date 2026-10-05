import base64
import os
from random import sample
from datetime import date

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import UserRole
from actas.models import Acta, ActaFieldValue, FormFieldDefinition, Signature, Site
from audit.models import ActaEvent


TEST_PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")
TEST_PDF = b"%PDF-1.4\n% ACTA DE PRUEBA\n%%EOF"
DEMO_PORTFOLIOS = (
    "Operaciones de Servicio",
    "Tecnología e Infraestructura",
    "Experiencia del Cliente",
    "Gestión Administrativa",
    "Analítica y Datos",
    "Recursos Humanos",
    "Continuidad del Negocio",
)


class Command(BaseCommand):
    help = "Crea siete actas ficticias para probar el flujo, solo en el entorno aislado."

    def handle(self, *args, **options):
        if settings.APP_ENV not in {"test", "testing", "staging"}:
            raise CommandError("Este comando solo funciona con APP_ENV=test/testing/staging.")

        User = get_user_model()
        with transaction.atomic():
            people = {
                "tech1": self._user(User, "demo_tecnico_001", "TECHNICIAN"),
                "tech2": self._user(User, "demo_tecnico_002", "TECHNICIAN"),
                "sup1": self._user(User, "demo_supervisor_001", "SUPERVISOR_ONE"),
                "sup2": self._user(User, "demo_supervisor_002", "SUPERVISOR_TWO"),
                "receiver1": self._user(User, "demo_receptor_001", "RECEIVER"),
                "receiver2": self._user(User, "demo_receptor_002", "RECEIVER"),
            }
            self._signature(people["sup1"].role_profile)
            self._signature(people["sup2"].role_profile)
            site, _ = Site.objects.get_or_create(code="PRUEBA", defaults={"name": "Sede ficticia de pruebas"})
            serial_field, _ = FormFieldDefinition.objects.get_or_create(
                key="demo_test_serial",
                defaults={"label": "Serial de prueba", "section": "equipo", "field_type": "text", "sort_order": 9000},
            )

            specs = [
                ("001", "PENDING_SUPERVISOR_ONE", "tech1", "receiver1", False, False, "PRUEBA-SERIAL-001"),
                ("002", "PENDING_SUPERVISOR_ONE", "tech2", "receiver2", False, False, "PRUEBA-SERIAL-002"),
                ("003", "PENDING_SUPERVISOR_TWO", "tech1", "receiver1", True, False, "PRUEBA-SERIAL-003"),
                ("004", "REJECTED_BY_SUPERVISOR_ONE", "tech2", "receiver2", False, False, "PRUEBA-SERIAL-004"),
                ("005", "PENDING_RECEIVER_UPLOAD", "tech1", "receiver1", True, False, "PRUEBA-SERIAL-005"),
                ("006", "PENDING_RECEIVER_UPLOAD", "tech2", "receiver2", True, False, "PRUEBA-SERIAL-006"),
                ("007", "COMPLETED", "tech1", "receiver1", True, True, "PRUEBA-SERIAL-007"),
            ]
            portfolio_names = sample(DEMO_PORTFOLIOS, k=len(specs))
            created = 0
            for (number, state, tech_key, receiver_key, reviewed, signed_scan, serial), portfolio in zip(specs, portfolio_names):
                case_number = f"PRUEBA-ACTA-{number}"
                if Acta.objects.filter(glpi_case_number=case_number).exists():
                    continue
                tech = people[tech_key]
                acta = Acta.objects.create(
                    status=state,
                    act_type="Entrega de prueba",
                    act_date=date.today(),
                    glpi_case_number=case_number,
                    portfolio=portfolio,
                    created_by=tech,
                    assigned_technician=tech,
                    supervisor_one=people["sup1"],
                    supervisor_two=people["sup2"],
                    receiver=people[receiver_key],
                    site=site,
                    rejection_reason="PRUEBA: corregir serial antes de reenviar." if state == "REJECTED_BY_SUPERVISOR_ONE" else "",
                    rejection_step="SUPERVISOR_ONE" if state == "REJECTED_BY_SUPERVISOR_ONE" else "",
                    completed_at=timezone.now() if state == "COMPLETED" else None,
                )
                ActaFieldValue.objects.create(acta=acta, definition=serial_field, value=serial, source="MANUAL", updated_by=tech)
                ActaEvent.objects.create(acta=acta, event_type="DEMO", action="TEST_FIXTURE_CREATED", actor=tech, to_status=state, metadata={"test_data": True})
                if reviewed:
                    self._approval(acta, "REVIEW", people["sup1"])
                if state in {"PENDING_RECEIVER_UPLOAD", "COMPLETED"}:
                    self._approval(acta, "FINAL_APPROVAL", people["sup2"])
                if state == "REJECTED_BY_SUPERVISOR_ONE":
                    Signature.objects.create(acta=acta, signature_type="REVIEW", signed_by=people["sup1"], signer_name="Demo Supervisor 001", result="REJECTED", rejection_reason=acta.rejection_reason, method="TEST")
                if signed_scan:
                    acta.pdf_file.save(f"{case_number}.pdf", ContentFile(TEST_PDF), save=False)
                    acta.save(update_fields=["pdf_file"])
                    Signature.objects.create(acta=acta, signature_type="RECEIVE", signed_by=people[receiver_key], signer_name=people[receiver_key].get_full_name() or people[receiver_key].username, signer_role="Receptor del activo", signature_hash="0" * 64, method="SCANNED_PDF", result="APPROVED")
                created += 1

        self.stdout.write(f"Listas {created} actas ficticias nuevas. Casos PRUEBA-ACTA-001 a PRUEBA-ACTA-007.")
        self.stdout.write("Usuarios demo_tecnico_001, demo_tecnico_002, demo_supervisor_001, demo_supervisor_002 y demo_receptor_001/002; sin contraseña asignada. Un administrador debe habilitar el acceso solo en pruebas.")

    @staticmethod
    def _user(User, username, role):
        user = User.objects.filter(username=username).first()
        if user is None:
            user = User(username=username, email=f"{username}@example.test")
            user.set_unusable_password()
            user.save()
        demo_password = os.getenv("DEMO_TEST_PASSWORD", "")
        if demo_password:
            user.set_password(demo_password)
            user.save(update_fields=["password"])
        profile, _ = UserRole.objects.get_or_create(user=user, defaults={"role": role})
        if profile.role != role:
            profile.role = role
            profile.save(update_fields=["role"])
        return user

    @staticmethod
    def _signature(profile):
        if not profile.digital_signature:
            profile.digital_signature.save("firma-demo.png", ContentFile(TEST_PNG), save=True)

    @staticmethod
    def _approval(acta, signature_type, user):
        signature = Signature.objects.create(
            acta=acta,
            signature_type=signature_type,
            signed_by=user,
            signer_name=user.get_full_name() or user.username,
            signer_role=user.role_profile.get_role_display(),
            signature_hash="0" * 64,
            method="DIGITAL_PNG",
            result="APPROVED",
        )
        signature.signature_image.save(f"demo-{acta.pk}-{signature_type}.png", ContentFile(TEST_PNG), save=True)

from datetime import timedelta
from hashlib import sha256
from random import sample

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import UserRole, WorkflowConfig
from actas.html_views import ensure_form_definitions
from actas.models import Acta, ActaFieldValue, FormFieldDefinition, PortfolioCatalog, Signature, Site
from audit.models import ActaEvent


PORTFOLIOS = (
    "Progreser2",
    "Banco W",
    "Jurídico",
    "Banco Unión",
    "Claro Móvil",
    "Tecnología",
    "Operaciones de Servicio",
    "Experiencia del Cliente",
)
EQUIPMENT = (
    ("Desktop", "Dell", "OptiPlex 7020", "Intel Core i5-14500", "16 GB DDR5", "SSD 512 GB", "Windows 11 Pro"),
    ("Portátil", "Lenovo", "ThinkPad E14 Gen 6", "Intel Core Ultra 5", "16 GB DDR5", "SSD 512 GB", "Windows 11 Pro"),
    ("Portátil", "HP", "ProBook 440 G10", "Intel Core i5-1335U", "16 GB DDR4", "SSD 512 GB", "Windows 11 Pro"),
    ("Desktop", "HP", "ProDesk 400 G9", "Intel Core i5-13500", "16 GB DDR4", "SSD 1 TB", "Windows 11 Pro"),
    ("Portátil", "Dell", "Latitude 5450", "Intel Core Ultra 5", "16 GB DDR5", "SSD 512 GB", "Windows 11 Pro"),
    ("Desktop", "Lenovo", "ThinkCentre M70s", "Intel Core i5-13400", "16 GB DDR4", "SSD 512 GB", "Windows 11 Pro"),
    ("Portátil", "Acer", "TravelMate P2", "Intel Core i5-1235U", "16 GB DDR4", "SSD 512 GB", "Windows 11 Pro"),
    ("Desktop", "Dell", "OptiPlex 7010", "Intel Core i5-13500", "16 GB DDR5", "SSD 512 GB", "Windows 11 Pro"),
)
PERIPHERALS = (
    ("Diadema", "Logitech", "H390 USB", "Diadema"),
    ("Teclado", "Logitech", "K120 USB", "Teclado"),
    ("Mouse", "Logitech", "M185 inalámbrico", "Mouse"),
    ("Otro", "Jabra", "Speak 510", "Parlante de conferencia"),
)
MONITORS = (
    ("Dell", "P2422H", "24 pulgadas IPS"),
    ("HP", "E24 G5", "23.8 pulgadas IPS"),
    ("Lenovo", "ThinkVision T24i", "23.8 pulgadas IPS"),
    ("LG", "24MP400", "23.8 pulgadas IPS"),
)
NAMES = (
    "Alex Prueba",
    "Sam Datos",
    "Taylor Muestra",
    "Robin Validación",
    "Cris Equipo",
    "Dani Proceso",
    "Ari Ejemplo",
    "Sol Sistema",
)


class Command(BaseCommand):
    help = "Crea ocho actas completas ficticias, solo en el entorno aislado de pruebas."

    def handle(self, *args, **options):
        if settings.APP_ENV not in {"test", "testing", "staging"}:
            raise CommandError("Este comando solo funciona con APP_ENV=test/testing/staging.")

        User = get_user_model()
        with transaction.atomic():
            ensure_form_definitions()
            technician_profiles = list(
                UserRole.objects.filter(role="TECHNICIAN", active=True, user__is_active=True)
                .select_related("user").order_by("user__username")
            )
            supervisor_one_profile = UserRole.objects.filter(
                role="SUPERVISOR_ONE", active=True, user__is_active=True
            ).select_related("user").order_by("user__username").first()
            supervisor_two_profile = UserRole.objects.filter(
                role="SUPERVISOR_TWO", active=True, user__is_active=True
            ).select_related("user").order_by("user__username").first()
            if not technician_profiles or not supervisor_one_profile or not supervisor_two_profile:
                raise CommandError("Crea primero un técnico y los dos supervisores activos en el entorno de pruebas.")

            receiver = self._receiver(User)
            supervisor_one = supervisor_one_profile.user
            supervisor_two = supervisor_two_profile.user
            workflow, _ = WorkflowConfig.objects.get_or_create(pk=1)
            if workflow.supervisor_one_id != supervisor_one.pk or workflow.supervisor_two_id != supervisor_two.pk:
                workflow.supervisor_one = supervisor_one
                workflow.supervisor_two = supervisor_two
                workflow.save(update_fields=["supervisor_one", "supervisor_two", "updated_at"])

            site, _ = Site.objects.get_or_create(
                code="DEMO-QA",
                defaults={"name": "Sede ficticia de pruebas"},
            )
            portfolio_names = sample(PORTFOLIOS, k=len(PORTFOLIOS))
            peripheral_specs = sample(PERIPHERALS * 2, k=len(PORTFOLIOS))
            for portfolio_name in portfolio_names:
                PortfolioCatalog.objects.get_or_create(name=portfolio_name)

            definitions = list(FormFieldDefinition.objects.filter(active=True).order_by("sort_order"))
            status_specs = [
                "PENDING_SUPERVISOR_ONE",
                "PENDING_SUPERVISOR_ONE",
                "PENDING_SUPERVISOR_ONE",
                "PENDING_SUPERVISOR_TWO",
                "PENDING_SUPERVISOR_TWO",
                "PENDING_RECEIVER_UPLOAD",
                "PENDING_RECEIVER_UPLOAD",
                "REJECTED_BY_SUPERVISOR_ONE",
            ]
            available = []
            new_count = 0
            for index, (portfolio, status) in enumerate(zip(portfolio_names, status_specs), start=1):
                case_number = f"PRUEBA-COMPLETA-{index:03d}"
                existing = Acta.objects.filter(glpi_case_number=case_number).first()
                if existing:
                    self.stdout.write(f"Ya existe {case_number}; se conserva sin cambios.")
                    available.append(existing)
                    continue

                technician = technician_profiles[(index - 1) % len(technician_profiles)].user
                equipment_type, brand, model, processor, ram, disk, operating_system = EQUIPMENT[index - 1]
                peripheral_label, peripheral_brand, peripheral_model, peripheral_name = peripheral_specs[index - 1]
                monitor_brand, monitor_model, monitor_description = MONITORS[(index - 1) % len(MONITORS)]
                person_name = NAMES[index - 1]
                serial = f"QA-{index:03d}-SYS"
                act_type = "Cambio" if index % 2 == 0 else "Entrega"
                previous_serial = f"QA-{index:03d}-OLD" if act_type == "Cambio" else "No aplica"

                acta = Acta.objects.create(
                    status=status,
                    act_type=act_type,
                    act_date=timezone.localdate() - timedelta(days=index),
                    glpi_case_number=case_number,
                    portfolio=portfolio,
                    created_by=technician,
                    assigned_technician=technician,
                    supervisor_one=supervisor_one,
                    supervisor_two=supervisor_two,
                    receiver=receiver,
                    site=site,
                    legal_custody_accepted=True,
                    legal_accuracy_confirmed=True,
                    legal_data_processing_accepted=True,
                    legal_accepted_at=timezone.now(),
                    completed_at=timezone.now() if status == "COMPLETED" else None,
                    rejection_reason="Prueba: validar corrección de campos y reenvío." if status == "REJECTED_BY_SUPERVISOR_ONE" else "",
                    rejection_step="SUPERVISOR_ONE" if status == "REJECTED_BY_SUPERVISOR_ONE" else "",
                )
                values = self._field_values(
                    index=index,
                    person_name=person_name,
                    portfolio=portfolio,
                    act_type=act_type,
                    previous_serial=previous_serial,
                    system_serial=serial,
                    equipment=(equipment_type, brand, model, processor, ram, disk, operating_system),
                    peripheral=(peripheral_label, peripheral_brand, peripheral_model, peripheral_name),
                    monitor=(monitor_brand, monitor_model, monitor_description),
                )
                for field in definitions:
                    value = values.get((field.section, field.label))
                    if value is None:
                        value = False if field.field_type == "boolean" else "No aplica"
                    ActaFieldValue.objects.create(
                        acta=acta,
                        definition=field,
                        value=value,
                        source="TEST",
                        updated_by=technician,
                    )

                self._signature(acta, "DELIVERY", technician, "Técnico asignado")
                if status in {"PENDING_SUPERVISOR_TWO", "PENDING_RECEIVER_UPLOAD"}:
                    self._signature(acta, "REVIEW", supervisor_one, "Supervisor uno")
                if status == "PENDING_RECEIVER_UPLOAD":
                    self._signature(acta, "FINAL_APPROVAL", supervisor_two, "Supervisor dos")
                if status == "REJECTED_BY_SUPERVISOR_ONE":
                    Signature.objects.create(
                        acta=acta,
                        signature_type="REVIEW",
                        signed_by=supervisor_one,
                        signer_name=supervisor_one.get_full_name() or supervisor_one.username,
                        signer_role="Supervisor uno",
                        result="REJECTED",
                        rejection_reason=acta.rejection_reason,
                        method="TEST",
                    )
                ActaEvent.objects.create(
                    acta=acta,
                    event_type="DEMO",
                    action="COMPLETE_TEST_ACTA_CREATED",
                    actor=technician,
                    to_status=status,
                    metadata={"test_data": True, "portfolio": portfolio, "peripheral": peripheral_label},
                )
                available.append(acta)
                new_count += 1

            self.stdout.write(f"Actas completas disponibles: {len(available)}; nuevas en esta ejecución: {new_count}")
            for acta in available:
                self.stdout.write(f"{acta.glpi_case_number}: {acta.portfolio} | {acta.act_type} | {acta.status}")
        self.stdout.write(f"Técnicos: {', '.join(profile.user.username for profile in technician_profiles)}; supervisores: {supervisor_one.username}, {supervisor_two.username}; receptor: {receiver.username}.")

    @staticmethod
    def _receiver(User):
        profile = UserRole.objects.filter(
            role="RECEIVER", active=True, user__is_active=True
        ).select_related("user").first()
        if profile:
            return profile.user
        user, _ = User.objects.get_or_create(
            username="demo_receptor_completo",
            defaults={
                "email": "demo_receptor_completo@example.test",
                "first_name": "Receptor",
                "last_name": "Pruebas",
            },
        )
        if not user.has_usable_password():
            user.set_unusable_password()
            user.save(update_fields=["password"])
        UserRole.objects.update_or_create(user=user, defaults={"role": "RECEIVER", "active": True})
        return user

    @staticmethod
    def _field_values(index, person_name, portfolio, act_type, previous_serial, system_serial, equipment, peripheral, monitor):
        equipment_type, brand, model, processor, ram, disk, operating_system = equipment
        peripheral_label, peripheral_brand, peripheral_model, peripheral_name = peripheral
        monitor_brand, monitor_model, monitor_description = monitor
        peripheral_values = {"Diadema": False, "Teclado": False, "Mouse": False, "CPU": False, "Móvil": False, "SIM": False, "Otro": False}
        peripheral_values[peripheral_label] = True
        return {
            ("usuario", "Nombre completo"): person_name,
            ("usuario", "Cédula"): f"990000{index:04d}",
            ("sistemas", "Tipo de cuenta"): "Red" if index % 2 else "Correo",
            ("sistemas", "Usuario de Windows"): f"qa.usuario{index:02d}",
            ("sistemas", "Cuenta de correo"): f"qa.usuario{index:02d}@example.test",
            ("sistemas", "Acceso a HelpDesk GLPI"): True,
            ("sistemas", "Novedades AIO"): index % 2 == 0,
            ("sistemas", "Impresora"): True,
            ("sistemas", "Control de acceso"): True,
            ("sistemas", "Recurso compartido"): True,
            ("sistemas", "Licencia Office 365"): True,
            ("sistemas", "Extensión"): f"51{index:02d}",
            ("sistemas", "Perfil de navegación"): "Estándar corporativo",
            ("sistemas", "Power BI"): index % 2 == 0,
            ("sistemas", "VPN"): index % 2 == 1,
            ("sistemas", "Acceso a red"): True,
            ("sistemas", "Acceso a correo"): True,
            ("equipo", "Tipo de equipo"): equipment_type,
            ("equipo", "Marca"): brand,
            ("equipo", "Modelo"): model,
            ("equipo", "Serial"): system_serial,
            ("equipo", "Serial devuelto"): previous_serial,
            ("equipo", "Procesador"): processor,
            ("equipo", "Dirección IP"): f"10.99.8.{30 + index}",
            ("equipo", "Memoria RAM"): ram,
            ("equipo", "Disco duro"): disk,
            ("equipo", "Sistema operativo"): operating_system,
            ("equipo", "Placa de inventario"): f"INV-QA-{index:04d}",
            **{("perifericos", label): value for label, value in peripheral_values.items()},
            ("perifericos", "¿Cuál es el otro periférico?"): peripheral_name if peripheral_label == "Otro" else "No aplica",
            ("perifericos", "Marca y modelo"): f"{peripheral_brand} {peripheral_model}",
            ("perifericos", "Placa de inventario GLPI"): f"INV-PER-{index:04d}",
            ("perifericos", "Serial"): f"PER-QA-{index:04d}",
            ("perifericos", "Serial devuelto"): f"No aplica para {act_type.lower()}",
            ("monitor", "Marca"): monitor_brand,
            ("monitor", "Modelo"): monitor_model,
            ("monitor", "Placa de inventario"): f"INV-MON-{index:04d}",
            ("monitor", "Serial"): f"MON-QA-{index:04d}",
            ("observaciones", "Observaciones"): f"Registro ficticio {index:02d}; proceso {portfolio}; datos de laboratorio.",
        }

    @staticmethod
    def _signature(acta, signature_type, user, role):
        signature = Signature.objects.create(
            acta=acta,
            signature_type=signature_type,
            signed_by=user,
            signer_name=user.get_full_name() or user.username,
            signer_role=role,
            signature_hash=sha256(f"{acta.glpi_case_number}:{signature_type}".encode()).hexdigest(),
            method="TEST",
            result="APPROVED",
        )
        return signature
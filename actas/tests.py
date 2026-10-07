import base64
import tempfile
import shutil
from io import StringIO
from unittest import skip
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from django.urls import resolve
from django.core.files.base import ContentFile

from accounts.models import UserRole, WorkflowConfig
from .models import Acta, ActaFieldValue, CampaignCatalog, FormFieldDefinition, PortfolioCatalog, Signature, Site


PNG_DATA = "data:image/png;base64," + "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="  # 1x1 PNG
TEST_MEDIA_ROOT = tempfile.mkdtemp(prefix="actas-test-media-")


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", MEDIA_ROOT=TEST_MEDIA_ROOT)
class SignatureAuthorizationTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.technician = user_model.objects.create_user("technician", password="pass123", email="tech@example.test")
        self.other_technician = user_model.objects.create_user("other-tech", password="pass123", email="other@example.test")
        self.supervisor_one = user_model.objects.create_user("supervisor-one", password="pass123", email="sup1@example.test")
        self.supervisor_two = user_model.objects.create_user("supervisor-two", password="pass123", email="sup2@example.test")
        self.receiver = user_model.objects.create_user("receiver", password="pass123", email="receiver@example.test")
        UserRole.objects.create(user=self.technician, role="TECHNICIAN")
        UserRole.objects.create(user=self.other_technician, role="TECHNICIAN")
        UserRole.objects.create(user=self.supervisor_one, role="SUPERVISOR_ONE")
        UserRole.objects.create(user=self.supervisor_two, role="SUPERVISOR_TWO")
        UserRole.objects.create(user=self.receiver, role="RECEIVER")
        WorkflowConfig.objects.update_or_create(pk=1, defaults={"supervisor_one": self.supervisor_one, "supervisor_two": self.supervisor_two})
        for supervisor in (self.supervisor_one, self.supervisor_two):
            supervisor.role_profile.digital_signature.save("supervisor.png", ContentFile(base64.b64decode(PNG_DATA.split(",", 1)[1])), save=True)
        for signer in (self.technician,):
            signer.role_profile.digital_signature.save("technician.png", ContentFile(base64.b64decode(PNG_DATA.split(",", 1)[1])), save=True)
        site = Site.objects.create(code="TEST", name="Sede de prueba")
        self.acta = Acta.objects.create(
            status="PENDING_SUPERVISOR_ONE",
            act_type="Entrega",
            act_date=timezone.localdate(),
            glpi_case_number="TEST-AUTH-001",
            portfolio="Pruebas",
            site=site,
            created_by=self.technician,
            assigned_technician=self.technician,
            supervisor_one=self.supervisor_one,
            supervisor_two=self.supervisor_two,
            receiver=self.receiver,
        )
        Signature.objects.create(
            acta=self.acta,
            signature_type="RECEIVE",
            signed_by=self.receiver,
            signer_name="Receptor",
            signer_role="Receptor del activo",
            signature_hash="receive-abc",
            method="DRAWN_PNG",
            result="APPROVED",
        )
        Signature.objects.create(acta=self.acta, signature_type="DELIVERY", signed_by=self.technician,
            signer_name="T?cnico", signer_role="T?cnico", signature_hash="abc", method="DIGITAL_PNG", result="APPROVED")


    def test_only_technicians_can_open_create_and_draft_preview(self):
        self.client.login(username="supervisor-one", password="pass123")
        self.assertEqual(self.client.get("/actas/new/").status_code, 403)
        self.assertEqual(self.client.post("/actas/preview-draft/", {}).status_code, 403)
        self.client.login(username="technician", password="pass123")
        self.assertEqual(self.client.get("/actas/new/").status_code, 200)

    def test_only_assigned_receiver_can_upload_the_physical_scan(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.acta.signatures.filter(signature_type="RECEIVE").delete()
        Signature.objects.create(acta=self.acta, signature_type="REVIEW", signed_by=self.supervisor_one, signer_name="Supervisor uno", result="APPROVED")
        Signature.objects.create(acta=self.acta, signature_type="FINAL_APPROVAL", signed_by=self.supervisor_two, signer_name="Supervisor dos", result="APPROVED")
        self.acta.status = "PENDING_RECEIVER_UPLOAD"
        self.acta.save(update_fields=["status"])
        self.client.login(username="technician", password="pass123")
        denied = self.client.post(f"/actas/{self.acta.public_id}/receiver-upload/", {
            "signed_scan": SimpleUploadedFile("signed.pdf", b"%PDF-1.4\n%%EOF", content_type="application/pdf"),
        })
        self.assertEqual(denied.status_code, 403)
        self.client.login(username="receiver", password="pass123")
        response = self.client.post(f"/actas/{self.acta.public_id}/receiver-upload/", {
            "signed_scan": SimpleUploadedFile("signed.pdf", b"%PDF-1.4\n%%EOF", content_type="application/pdf"),
        })
        self.assertEqual(response.status_code, 302)
        signature = Signature.objects.get(acta=self.acta, signature_type="RECEIVE")
        self.assertEqual(signature.signed_by, self.receiver)
        self.assertEqual(signature.method, "SCANNED_PDF")
        self.assertEqual(Acta.objects.get(pk=self.acta.pk).status, "COMPLETED")

    def test_receiver_cannot_post_a_drawn_signature_instead_of_a_scan(self):
        self.acta.signatures.filter(signature_type="RECEIVE").delete()
        self.client.login(username="receiver", password="pass123")
        self.client.post(f"/actas/{self.acta.public_id}/sign/", {
            "signature_type": "RECEIVE", "signer_name": "Receptor", "signature_data": PNG_DATA,
        })
        self.assertFalse(Signature.objects.filter(acta=self.acta, signature_type="RECEIVE").exists())

    def test_detail_action_cannot_complete_acta_without_a_signature(self):
        self.client.login(username="supervisor-one", password="pass123")
        response = self.client.post(f"/actas/{self.acta.public_id}/", {"action": "approve"})
        self.assertEqual(response.status_code, 403)
        self.acta.refresh_from_db()
        self.assertEqual(self.acta.status, "PENDING_SUPERVISOR_ONE")
        self.assertFalse(Signature.objects.filter(acta=self.acta, signature_type="REVIEW").exists())

    def test_technician_cannot_sign_for_either_supervisor(self):
        self.client.force_login(self.technician)
        response = self.client.post(
            f"/api/actas/{self.acta.public_id}/review/approve/",
            {},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            Signature.objects.filter(acta=self.acta, signature_type="REVIEW").exists()
        )

        Signature.objects.create(
            acta=self.acta,
            signature_type="REVIEW",
            signed_by=self.supervisor_one,
            signer_name="Supervisor uno",
            result="APPROVED",
        )
        self.acta.status = "PENDING_SUPERVISOR_TWO"
        self.acta.save(update_fields=["status"])
        response = self.client.post(
            f"/api/actas/{self.acta.public_id}/final-approval/approve/",
            {},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            Signature.objects.filter(
                acta=self.acta,
                signature_type="FINAL_APPROVAL",
            ).exists()
        )

        response = self.client.post(
            f"/actas/{self.acta.public_id}/sign/",
            {"signature_type": "REVIEW"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            Signature.objects.filter(acta=self.acta, signature_type="REVIEW").count(),
            1,
        )
        self.assertEqual(
            Signature.objects.get(acta=self.acta, signature_type="REVIEW").signed_by,
            self.supervisor_one,
        )

    @override_settings(IS_TEST_ENVIRONMENT=False)
    def test_delivery_and_review_notify_the_correct_supervisors(self):
        from django.core import mail
        from notifications.models import Notification
        from notifications.services import notify_signature_saved

        delivery = Signature.objects.get(acta=self.acta, signature_type="DELIVERY")
        notify_signature_saved(self.acta, delivery, actor=self.technician)
        first_notification = Notification.objects.get(
            acta=self.acta,
            recipient=self.supervisor_one,
        )
        self.assertEqual(first_notification.title, "Revisión pendiente")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.supervisor_one.email])

        review = Signature.objects.create(
            acta=self.acta,
            signature_type="REVIEW",
            signed_by=self.supervisor_one,
            signer_name="Supervisor uno",
            result="APPROVED",
        )
        notify_signature_saved(self.acta, review, actor=self.supervisor_one)
        second_notification = Notification.objects.get(
            acta=self.acta,
            recipient=self.supervisor_two,
        )
        self.assertEqual(second_notification.title, "Aprobación final pendiente")
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[1].to, [self.supervisor_two.email])

    def test_user_cannot_read_another_technicians_acta(self):
        self.client.login(username="other-tech", password="pass123")
        response = self.client.get(f"/actas/{self.acta.public_id}/")
        self.assertEqual(response.status_code, 404)

    def test_assigned_user_can_render_acta_preview(self):
        self.client.login(username="technician", password="pass123")
        response = self.client.get(f"/actas/{self.acta.public_id}/preview/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Recibe")
        self.assertContains(response, "Firma registrada")
        self.assert_acta_document_order(response.content.decode("utf-8"))
        self.client.login(username="supervisor-one", password="pass123")
        detail = self.client.get(f"/actas/{self.acta.public_id}/")
        self.assertEqual(detail.status_code, 200)
        self.assert_acta_document_order(detail.content.decode("utf-8"))
        self.assertEqual(self.client.get(f"/actas/{self.acta.public_id}/sign/").status_code, 200)
        self.client.login(username="supervisor-two", password="pass123")
        self.assertEqual(self.client.get(f"/actas/{self.acta.public_id}/sign/").status_code, 200)

    def test_complete_acta_pdf_uses_letter_paper_and_keeps_content(self):
        from random import choice

        from accounts.management.commands.seed_demo_actas import DEMO_PORTFOLIOS
        from django.template.loader import render_to_string
        from weasyprint import HTML
        from .html_views import _acta_document_context, ensure_form_definitions

        self.acta.portfolio = choice(DEMO_PORTFOLIOS)
        self.acta.save(update_fields=["portfolio"])
        ensure_form_definitions()
        sample_values = {
            "Nombre completo": "María Prueba",
            "Cédula": "1234567890",
            "Tipo de cuenta": "Red",
            "Cuenta de correo": "maria.prueba@example.test",
            "Marca": "Dell",
            "Modelo": "Latitude 5450",
            "Serial": "LT5450-PRUEBA",
            "Observaciones": "Acta completa de validación de impresión en carta.",
        }
        definitions = FormFieldDefinition.objects.filter(active=True)
        for definition in definitions:
            value = sample_values.get(definition.label)
            if value is None:
                value = True if definition.field_type == "boolean" else "Dato de prueba"
            ActaFieldValue.objects.update_or_create(
                acta=self.acta,
                definition=definition,
                defaults={"value": value, "source": "TEST", "updated_by": self.technician},
            )
        self.acta.signatures.filter(signature_type="RECEIVE").delete()
        for signature_type, signer, name, role in (
            ("REVIEW", self.supervisor_one, "Supervisor de Prueba", "Analista de Procesos"),
            ("FINAL_APPROVAL", self.supervisor_two, "Aprobador de Prueba", "Director de Tecnología"),
            ("RECEIVE", self.receiver, "María Prueba", "Usuaria"),
        ):
            Signature.objects.create(
                acta=self.acta,
                signature_type=signature_type,
                signed_by=signer,
                signer_name=name,
                signer_role=role,
                result="APPROVED",
                method="TEST",
            )

        markup = render_to_string("actas/_acta_document.html", {
            "acta": self.acta,
            **_acta_document_context(self.acta),
        })
        self.assertIn("María Prueba", markup)
        self.assertIn("LT5450-PRUEBA", markup)
        self.assertIn("Director de Tecnología", markup)
        self.assertIn(self.acta.portfolio, markup)
        rendered_pdf = HTML(string=markup).render()
        pdf_bytes = rendered_pdf.write_pdf()
        self.assertTrue(pdf_bytes.startswith(b"%PDF-"))
        self.assertGreaterEqual(len(rendered_pdf.pages), 1)
        for page in rendered_pdf.pages:
            self.assertAlmostEqual(page.width, 816, delta=1)
            self.assertAlmostEqual(page.height, 1056, delta=1)

    @override_settings(APP_ENV="testing")
    def test_complete_test_seed_populates_all_fields_and_varied_assets(self):
        from django.core.management import call_command

        call_command("seed_complete_test_actas")
        call_command("seed_complete_test_actas")
        actas = list(Acta.objects.filter(glpi_case_number__startswith="PRUEBA-COMPLETA-").order_by("glpi_case_number"))
        self.assertEqual(len(actas), 8)
        self.assertEqual(len({acta.portfolio for acta in actas}), 8)
        active_definitions = list(FormFieldDefinition.objects.filter(active=True))
        portfolios = set(PortfolioCatalog.objects.filter(active=True).values_list("name", flat=True))
        selected_peripheral_labels = set()
        for acta in actas:
            values = {
                (row.definition.section, row.definition.label): row.value
                for row in acta.field_values.select_related("definition")
            }
            self.assertEqual(len(values), len(active_definitions))
            self.assertTrue(all(value not in (None, "") for value in values.values()))
            self.assertIn(acta.portfolio, portfolios)
            selected_peripherals = [
                values[("perifericos", label)]
                for label in ("Diadema", "Teclado", "Mouse", "Otro")
            ]
            self.assertEqual(sum(selected_peripherals), 1)
            selected_peripheral_labels.add(("Diadema", "Teclado", "Mouse", "Otro")[selected_peripherals.index(True)])
            for label in ("Marca", "Modelo", "Placa de inventario", "Serial"):
                self.assertTrue(values[("monitor", label)])
        self.assertGreater(len(selected_peripheral_labels), 1)

    def assert_acta_document_order(self, html):
        tokens = ["ACTA DE ENTREGA", "Usuarios", "Desktop o port", "Perif", "Monitor", "Observaciones", "Compromisos", "Firmas"]
        positions = [html.index(token) for token in tokens]
        self.assertEqual(positions, sorted(positions))

    def test_staff_technician_is_blocked_from_django_admin(self):
        self.technician.is_staff = True
        self.technician.save(update_fields=["is_staff"])
        self.client.login(username="technician", password="pass123")
        self.assertEqual(self.client.get("/admin/").status_code, 403)

    def test_authenticated_supervisor_can_reach_admin_login_form(self):
        self.client.login(username="supervisor-one", password="pass123")
        response = self.client.get("/admin/")
        self.assertRedirects(response, "/admin/login/?next=/admin/", fetch_redirect_response=False)
        self.assertEqual(self.client.get(response.url).status_code, 200)

    def test_anonymous_user_is_redirected_to_django_admin_login(self):
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/admin/login/?next=/admin/")

    def test_shared_logout_works_across_main_views_for_each_role(self):
        auditor = get_user_model().objects.create_user("auditor", password="pass123")
        UserRole.objects.create(user=auditor, role="AUDITOR")
        administrator = get_user_model().objects.create_superuser("logout-admin", "admin@example.test", "pass123")
        acta_url = f"/actas/{self.acta.public_id}"
        role_views = [
            (self.technician, ["/accounts/dashboard/", "/actas/", "/actas/new/", "/accounts/supervisor-signature/", f"{acta_url}/", f"{acta_url}/preview/", f"{acta_url}/sign/", "/accounts/notifications/"]),
            (self.supervisor_one, ["/accounts/dashboard/", "/actas/", "/actas/review/", "/accounts/supervisor-signature/", f"{acta_url}/", f"{acta_url}/preview/", f"{acta_url}/sign/", "/accounts/reports/", "/accounts/notifications/"]),
            (self.supervisor_two, ["/accounts/dashboard/", "/actas/", "/actas/review/", "/accounts/supervisor-signature/", f"{acta_url}/", f"{acta_url}/preview/", f"{acta_url}/sign/", "/accounts/reports/", "/accounts/notifications/"]),
            (administrator, ["/accounts/dashboard/", "/actas/", f"{acta_url}/", f"{acta_url}/preview/", "/accounts/reports/", "/accounts/notifications/"]),
            (auditor, ["/accounts/dashboard/", "/actas/", f"{acta_url}/", f"{acta_url}/preview/", "/accounts/reports/", "/accounts/notifications/"]),
        ]

        for user, view_paths in role_views:
            for view_path in view_paths:
                with self.subTest(role=user.username, view=view_path):
                    self.client.force_login(user)
                    page = self.client.get(view_path)
                    self.assertEqual(page.status_code, 200)
                    self.assertContains(page, 'action="/logout/"')
                    response = self.client.post("/logout/")
                    self.assertRedirects(response, "/login/")
                    self.assertNotIn("_auth_user_id", self.client.session)

                self.client.force_login(self.technician)
                draft_preview = self.client.post("/actas/preview-draft/", {})
                self.assertEqual(draft_preview.status_code, 200)
                self.assertContains(draft_preview, 'action="/logout/"')
                response = self.client.post("/logout/")
                self.assertRedirects(response, "/login/")
                self.assertNotIn("_auth_user_id", self.client.session)

    def test_django_admin_logout_redirects_to_application_login(self):
        administrator = get_user_model().objects.create_superuser("admin-logout", "admin@example.test", "pass123")
        self.client.force_login(administrator)
        page = self.client.get("/admin/")
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'action="/admin/logout/"')
        response = self.client.post("/admin/logout/")
        self.assertRedirects(response, "/login/")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_shared_logout_form_passes_csrf_validation(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.technician)
        page = client.get("/accounts/dashboard/")
        self.assertEqual(page.status_code, 200)
        csrf_token = client.cookies["csrftoken"].value
        response = client.post("/logout/", {"csrfmiddlewaretoken": csrf_token})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/login/")
        self.assertNotIn("_auth_user_id", client.session)

    def test_stale_login_csrf_token_returns_fresh_login_form(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post("/login/", {"username": "technician", "password": "pass123"})
        self.assertRedirects(response, "/login/", fetch_redirect_response=False)
        login_page = client.get(response.url)
        self.assertEqual(login_page.status_code, 200)
        self.assertContains(login_page, "El formulario de acceso venció")
        self.assertContains(login_page, 'name="csrfmiddlewaretoken"')
        self.assertIn("csrftoken", client.cookies)

    def test_admin_dashboard_loads_synerjoy_theme_and_admin_modules(self):
        administrator = get_user_model().objects.create_superuser("site-admin", "admin@example.test", "pass123")
        self.client.login(username=administrator.username, password="pass123")
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 200)
        self.assertRegex(response.content.decode(), r"accounts/css/admin(?:\.[\w]+)?\.css")
        self.assertContains(response, "Synerjoy")
        self.assertContains(response, "Actas")

    @override_settings(APP_ENV="testing")
    def test_demo_seed_creates_seven_identifiable_fake_actas_idempotently(self):
        from django.core.management import call_command
        output = StringIO()
        call_command("seed_demo_actas", stdout=output)
        call_command("seed_demo_actas", stdout=StringIO())
        demos = Acta.objects.filter(glpi_case_number__startswith="PRUEBA-ACTA-")
        self.assertEqual(demos.count(), 7)
        self.assertEqual(demos.filter(status="PENDING_RECEIVER_SIGNATURE").count(), 1)
        self.assertEqual(demos.filter(status="PENDING_TECHNICIAN_DELIVERY").count(), 1)
        self.assertEqual(demos.filter(status="PENDING_SUPERVISOR_TWO").count(), 2)
        self.assertFalse(demos.filter(status="PENDING_RECEIVER_UPLOAD").exists())
        self.assertEqual(demos.values("portfolio").distinct().count(), 7)

    def test_supervisor_can_upload_png_signature_and_approval_uses_it(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.client.login(username="supervisor-one", password="pass123")
        response = self.client.post("/accounts/supervisor-signature/", {
            "signature": SimpleUploadedFile("firma.png", base64.b64decode(PNG_DATA.split(",", 1)[1]), content_type="image/png"),
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn(".png", self.supervisor_one.role_profile.digital_signature.name)
        self.acta.status = "PENDING_SUPERVISOR_ONE"
        self.acta.save(update_fields=["status"])
        response = self.client.post(f"/actas/{self.acta.public_id}/sign/", {"signature_type": "REVIEW", "signer_name": "Supervisor uno"})
        self.assertEqual(response.status_code, 302)
        signature = Signature.objects.get(acta=self.acta, signature_type="REVIEW", result="APPROVED")
        self.assertEqual(signature.method, "DIGITAL_PNG")
        self.assertTrue(signature.signature_image.name.endswith(".png"))

    def test_form_definitions_api_route_does_not_resolve_as_acta_detail(self):
        match = resolve("/api/actas/field-definitions/")
        self.assertEqual(match.view_name, "field-definition-list")

    def test_api_list_only_returns_actas_assigned_to_the_technician(self):
        Acta.objects.create(
            status="DRAFT",
            act_type="Entrega",
            act_date=timezone.localdate(),
            glpi_case_number="TEST-AUTH-002",
            portfolio="Pruebas",
            created_by=self.other_technician,
            assigned_technician=self.other_technician,
        )
        self.client.login(username="technician", password="pass123")
        response = self.client.get("/api/actas/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["glpi_case_number"] for row in response.json()], [self.acta.glpi_case_number])

    def test_api_rejects_drawn_receive_signature(self):
        self.client.login(username="receiver", password="pass123")
        response = self.client.post(f"/api/actas/{self.acta.public_id}/receive/sign/", {}, content_type="application/json")
        self.assertEqual(response.status_code, 410)

    def test_api_requires_receiver_to_upload_scanned_pdf_after_approval(self):
        draft = Acta.objects.create(
            status="DRAFT", act_type="Entrega", act_date=timezone.localdate(),
            glpi_case_number="TEST-API-SIGN-001", created_by=self.technician,
            assigned_technician=self.technician, receiver=self.receiver,
        )
        self.client.login(username="receiver", password="pass123")
        response = self.client.post(f"/api/actas/{draft.public_id}/receive/sign/", {}, content_type="application/json")
        self.assertEqual(response.status_code, 410)
        self.assertEqual(Acta.objects.get(pk=draft.pk).status, "DRAFT")
        self.assertFalse(Signature.objects.filter(acta=draft, signature_type="RECEIVE").exists())

    def test_glpi_autocomplete_returns_formatted_mock_data(self):
        self.client.login(username="technician", password="pass123")
        response = self.client.get("/actas/glpi/autocomplete/?case_number=45084")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["simulation"])
        self.assertEqual(payload["case"]["case_number"], "45084")
        self.assertIn("Diadema", payload["fields"])

    def test_create_acta_stores_required_form_fields_atomically(self):
        from .html_views import ensure_form_definitions

        ensure_form_definitions()
        required_fields = FormFieldDefinition.objects.filter(active=True, required=True)
        form_data = {
            "act_date": timezone.localdate().isoformat(),
            "act_type": "Entrega",
            "glpi_case_number": "TEST-CREATE-001",
            "portfolio": "Pruebas",
            "legal_custody_accepted": "on",
            "legal_accuracy_confirmed": "on",
            "legal_data_processing_accepted": "on",
        }
        for field in required_fields:
            form_data[f"field_{field.key}"] = "Dato de prueba"
        self.client.login(username="technician", password="pass123")
        with patch("actas.html_views.GlpiClient.get_case", return_value={"email": self.receiver.email}):
            response = self.client.post("/actas/new/", form_data)
        self.assertEqual(response.status_code, 302)
        acta = Acta.objects.get(glpi_case_number="TEST-CREATE-001")
        self.assertEqual(acta.assigned_technician, self.technician)
        self.assertEqual(acta.receiver, self.receiver)
        self.assertEqual(acta.supervisor_one, self.supervisor_one)
        self.assertEqual(acta.supervisor_two, self.supervisor_two)
        self.assertEqual(acta.status, "PENDING_RECEIVER_SIGNATURE")
        self.assertFalse(Signature.objects.filter(acta=acta, result="APPROVED").exists())
        self.assertEqual(ActaFieldValue.objects.filter(acta=acta).count(), required_fields.count())
        self.assertTrue(acta.legal_custody_accepted and acta.legal_accuracy_confirmed and acta.legal_data_processing_accepted)
        self.assertIsNotNone(acta.legal_accepted_at)

    def test_campaign_options_are_loaded_saved_and_shown_in_acta_detail(self):
        from .html_views import ensure_form_definitions

        portfolio = PortfolioCatalog.objects.create(
            name="Portafolio de integración",
            defaults={
                "Acceso a HelpDesk GLPI": True,
                "VPN": False,
            },
        )
        second_portfolio = PortfolioCatalog.objects.create(
            name="Portafolio de integración alterno",
            defaults={"Power BI": True},
        )
        campaign = CampaignCatalog.objects.create(
            name="Campaña de integración",
            portfolio=portfolio,
            active=True,
        )
        second_campaign = CampaignCatalog.objects.create(
            name="Campaña de integración alterna",
            portfolio=second_portfolio,
            active=True,
        )
        CampaignCatalog.objects.create(name="Campaña inactiva", active=False)
        self.client.force_login(self.technician)

        form = self.client.get("/actas/new/")
        self.assertEqual(form.status_code, 200)
        self.assertContains(form, f'<option value="{campaign.pk}"')
        self.assertContains(form, campaign.name)
        self.assertNotContains(form, "Campaña inactiva")
        self.assertContains(form, 'name="campaign_id"')
        self.assertContains(form, "readonly")
        self.assertNotContains(form, 'name="receiver_id"')

        campaign_response = self.client.get(
            f"/actas/campaigns/autocomplete/?campaign_id={campaign.pk}"
        )
        self.assertEqual(campaign_response.status_code, 200)
        self.assertEqual(campaign_response.json()["portfolio"], portfolio.name)
        self.assertEqual(
            campaign_response.json()["fields"],
            {"Acceso a HelpDesk GLPI": True, "VPN": False},
        )
        second_campaign_response = self.client.get(
            f"/actas/campaigns/autocomplete/?campaign_id={second_campaign.pk}"
        )
        self.assertEqual(second_campaign_response.status_code, 200)
        self.assertEqual(second_campaign_response.json()["portfolio"], second_portfolio.name)
        self.assertEqual(second_campaign_response.json()["fields"], {"Power BI": True})

        unmapped_campaign = CampaignCatalog.objects.create(
            name="Campaña sin relación",
            active=True,
        )
        unmapped_response = self.client.get(
            f"/actas/campaigns/autocomplete/?campaign_id={unmapped_campaign.pk}"
        )
        self.assertEqual(unmapped_response.status_code, 409)

        missing_campaign = self.client.post(
            "/actas/new/",
            {"glpi_case_number": "TEST-CAMPAIGN-MISSING"},
        )
        self.assertEqual(missing_campaign.status_code, 400)
        self.assertContains(missing_campaign, campaign.name, status_code=400)
        self.assertContains(missing_campaign, "Selecciona una campaña activa.", status_code=400)

        ensure_form_definitions()
        form_data = {
            "act_date": timezone.localdate().isoformat(),
            "act_type": "Entrega",
            "glpi_case_number": "TEST-CAMPAIGN-001",
            "portfolio": "Valor enviado no confiable",
            "campaign_id": str(campaign.pk),
            "legal_custody_accepted": "on",
            "legal_accuracy_confirmed": "on",
            "legal_data_processing_accepted": "on",
        }
        for field in FormFieldDefinition.objects.filter(active=True, required=True):
            form_data[f"field_{field.key}"] = "Dato de prueba"
        helpdesk_definition = FormFieldDefinition.objects.get(
            label="Acceso a HelpDesk GLPI",
            section="sistemas",
        )
        form_data[f"field_{helpdesk_definition.key}"] = "on"

        with patch("actas.html_views.GlpiClient.get_case", return_value={"email": self.receiver.email}):
            response = self.client.post("/actas/new/", form_data)
        self.assertEqual(response.status_code, 302)
        acta = Acta.objects.get(glpi_case_number=form_data["glpi_case_number"])
        self.assertEqual(acta.campaign, campaign)
        self.assertEqual(acta.portfolio, portfolio.name)
        saved_fields = {
            field.definition.label: field.value
            for field in acta.field_values.select_related("definition")
        }
        self.assertTrue(saved_fields["Acceso a HelpDesk GLPI"])

        form_data["glpi_case_number"] = "TEST-CAMPAIGN-002"
        form_data["campaign_id"] = str(second_campaign.pk)
        form_data[f"field_{helpdesk_definition.key}"] = ""
        power_bi_definition = FormFieldDefinition.objects.get(
            label="Power BI",
            section="sistemas",
        )
        form_data[f"field_{power_bi_definition.key}"] = "on"
        with patch("actas.html_views.GlpiClient.get_case", return_value={"email": self.receiver.email}):
            response = self.client.post("/actas/new/", form_data)
        self.assertEqual(response.status_code, 302)
        second_acta = Acta.objects.get(glpi_case_number=form_data["glpi_case_number"])
        self.assertEqual(second_acta.campaign, second_campaign)
        self.assertEqual(second_acta.portfolio, second_portfolio.name)
        self.assertTrue(
            second_acta.field_values.get(definition=power_bi_definition).value
        )

        detail = self.client.get(f"/actas/{acta.public_id}/")
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "Campaña")
        self.assertContains(detail, campaign.name)

        api_response = self.client.get("/api/actas/")
        self.assertEqual(api_response.status_code, 200)
        api_acta = next(item for item in api_response.json() if item["public_id"] == str(acta.public_id))
        self.assertEqual(api_acta["campaign"], campaign.pk)

    def test_receiver_is_resolved_from_glpi_email_for_each_technician(self):
        from .html_views import ensure_form_definitions

        second_receiver = get_user_model().objects.create_user(
            "second-receiver", email="second-receiver@example.test", password="pass123"
        )
        UserRole.objects.create(user=second_receiver, role="RECEIVER")
        ensure_form_definitions()
        required_fields = FormFieldDefinition.objects.filter(active=True, required=True)
        self.other_technician.role_profile.digital_signature.save(
            "other-technician.png",
            ContentFile(base64.b64decode(PNG_DATA.split(",", 1)[1])),
            save=True,
        )

        for index, technician in enumerate((self.technician, self.other_technician), start=1):
            with self.subTest(technician=technician.username):
                self.client.force_login(technician)
                response = self.client.get("/actas/new/")
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, 'name="receiver_id"')

                response = self.client.post("/actas/new/", {"glpi_case_number": ""})
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, 'name="receiver_id"')

                form_data = {
                    "act_date": timezone.localdate().isoformat(),
                    "act_type": "Entrega",
                    "glpi_case_number": f"TEST-RECEIVER-{index}",
                    "portfolio": "Pruebas",
                    "legal_custody_accepted": "on",
                    "legal_accuracy_confirmed": "on",
                    "legal_data_processing_accepted": "on",
                }
                for field in required_fields:
                    form_data[f"field_{field.key}"] = "Dato de prueba"
                with patch(
                    "actas.html_views.GlpiClient.get_case",
                    return_value={"email": second_receiver.email.upper()},
                ):
                    response = self.client.post("/actas/new/", form_data)
                self.assertEqual(response.status_code, 302)
                acta = Acta.objects.get(glpi_case_number=form_data["glpi_case_number"])
                self.assertEqual(acta.receiver, second_receiver)
                self.assertEqual(acta.status, "PENDING_RECEIVER_SIGNATURE")
                self.assertFalse(acta.signatures.filter(result="APPROVED").exists())

    def test_acta_creation_rejects_missing_or_ambiguous_glpi_receiver(self):
        from .html_views import ensure_form_definitions

        ensure_form_definitions()
        form_data = {
            "act_date": timezone.localdate().isoformat(),
            "act_type": "Entrega",
            "glpi_case_number": "TEST-RECEIVER-INVALID",
            "portfolio": "Pruebas",
            "legal_custody_accepted": "on",
            "legal_accuracy_confirmed": "on",
            "legal_data_processing_accepted": "on",
        }
        for field in FormFieldDefinition.objects.filter(active=True, required=True):
            form_data[f"field_{field.key}"] = "Dato de prueba"
        self.client.force_login(self.technician)

        invalid_cases = (
            ("TEST-RECEIVER-NO-MATCH", {"email": "unknown@example.test"}),
            ("TEST-RECEIVER-NO-EMAIL", {"email": ""}),
        )
        for case_number, glpi_case in invalid_cases:
            with self.subTest(case=case_number):
                form_data["glpi_case_number"] = case_number
                with patch("actas.html_views.GlpiClient.get_case", return_value=glpi_case):
                    response = self.client.post("/actas/new/", form_data)
                self.assertEqual(response.status_code, 400)
                self.assertFalse(Acta.objects.filter(glpi_case_number=case_number).exists())

        duplicate_receiver = get_user_model().objects.create_user(
            "duplicate-receiver",
            email=self.receiver.email,
        )
        UserRole.objects.create(user=duplicate_receiver, role="RECEIVER")
        form_data["glpi_case_number"] = "TEST-RECEIVER-DUPLICATE"
        with patch(
            "actas.html_views.GlpiClient.get_case",
            return_value={"email": self.receiver.email},
        ):
            response = self.client.post("/actas/new/", form_data)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Acta.objects.filter(glpi_case_number="TEST-RECEIVER-DUPLICATE").exists())

    def test_create_acta_requires_all_legal_consents(self):
        self.client.login(username="technician", password="pass123")
        response = self.client.post("/actas/new/", {
            "act_date": timezone.localdate().isoformat(), "act_type": "Entrega",
            "glpi_case_number": "TEST-CREATE-NO-CONSENT",
        })
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Acta.objects.filter(glpi_case_number="TEST-CREATE-NO-CONSENT").exists())

    @skip("El flujo antiguo firmaba ambos supervisores antes de la recepción; el flujo actual se prueba de extremo a extremo en test_ordered_tablet_signature_flow_notifies_each_role_and_generates_letter_pdf.")
    def test_complete_signature_flow_waits_for_receiver_scan_before_completion(self):
        self.acta.status = "PENDING_SUPERVISOR_ONE"
        self.acta.save()
        self.client.login(username="supervisor-one", password="pass123")
        self.client.post(f"/actas/{self.acta.public_id}/sign/", {"signature_type": "REVIEW", "signer_name": "Supervisor uno"})
        self.acta.refresh_from_db()
        self.assertEqual(self.acta.status, "PENDING_SUPERVISOR_TWO")
        self.client.login(username="supervisor-two", password="pass123")
        self.client.post(f"/actas/{self.acta.public_id}/sign/", {"signature_type": "FINAL_APPROVAL", "signer_name": "Supervisor dos"})
        self.acta.refresh_from_db()
        self.assertEqual(self.acta.status, "PENDING_RECEIVER_UPLOAD")
        self.assertIsNone(self.acta.completed_at)
        self.client.login(username="receiver", password="pass123")
        from django.core.files.uploadedfile import SimpleUploadedFile
        pdf = SimpleUploadedFile("acta-prueba.pdf", b"%PDF-1.4\nprueba\n%%EOF", content_type="application/pdf")
        response = self.client.post(f"/actas/{self.acta.public_id}/receiver-upload/", {"signed_scan": pdf})
        self.assertEqual(response.status_code, 302)
        self.acta.refresh_from_db()
        self.assertEqual(self.acta.status, "COMPLETED")
        self.assertIsNotNone(self.acta.completed_at)
        self.assertTrue(self.acta.pdf_file)
        self.assertEqual(self.acta.signatures.filter(result="APPROVED").count(), 4)

    @override_settings(IS_TEST_ENVIRONMENT=False, GLPI_UPLOAD_ENABLED=False)
    def test_ordered_tablet_signature_flow_notifies_each_role_and_generates_letter_pdf(self):
        from notifications.models import Notification

        self.acta.signatures.all().delete()
        self.acta.status = "PENDING_RECEIVER_SIGNATURE"
        self.acta.save(update_fields=["status"])
        receiver_url = f"/actas/receiver/sign/{self.acta.receiver_signature_token}/"
        self.assertEqual(self.client.get(receiver_url).status_code, 200)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(receiver_url, {"signature_data": PNG_DATA})
        self.assertEqual(response.status_code, 200)
        self.acta.refresh_from_db()
        self.assertEqual(self.acta.status, "PENDING_TECHNICIAN_DELIVERY")
        receive = Signature.objects.get(acta=self.acta, signature_type="RECEIVE")
        self.assertEqual(receive.method, "DRAWN_PNG")
        self.assertEqual(receive.signed_by, self.receiver)
        self.assertEqual(Notification.objects.get(acta=self.acta, recipient=self.technician).title, "Firma del receptor registrada")

        self.client.force_login(self.technician)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(f"/actas/{self.acta.public_id}/sign/", {"signature_type": "DELIVERY"})
        self.assertEqual(response.status_code, 302)
        self.acta.refresh_from_db()
        self.assertEqual(self.acta.status, "PENDING_SUPERVISOR_ONE")
        self.assertEqual(Notification.objects.get(acta=self.acta, recipient=self.supervisor_one).title, "Revisión pendiente")

        self.client.force_login(self.supervisor_one)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(f"/actas/{self.acta.public_id}/sign/", {"signature_type": "REVIEW"})
        self.assertEqual(response.status_code, 302)
        self.acta.refresh_from_db()
        self.assertEqual(self.acta.status, "PENDING_SUPERVISOR_TWO")
        self.assertEqual(Notification.objects.get(acta=self.acta, recipient=self.supervisor_two).title, "Aprobación final pendiente")

        self.client.force_login(self.supervisor_two)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(f"/actas/{self.acta.public_id}/sign/", {"signature_type": "FINAL_APPROVAL"})
        self.assertEqual(response.status_code, 302)
        self.acta.refresh_from_db()
        self.assertEqual(self.acta.status, "COMPLETED")
        self.assertIsNotNone(self.acta.completed_at)
        self.assertTrue(self.acta.pdf_file)
        self.assertTrue(self.acta.pdf_file.read().startswith(b"%PDF-"))
        self.assertEqual(
            list(self.acta.signatures.filter(result="APPROVED").order_by("signed_at").values_list("signature_type", flat=True)),
            ["RECEIVE", "DELIVERY", "REVIEW", "FINAL_APPROVAL"],
        )

    @override_settings(GLPI_UPLOAD_ENABLED=False)
    @skip("El flujo de escaneo legado fue sustituido por la firma de recepción en tablet.")
    def test_end_to_end_acta_creation_and_completion_across_roles(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .html_views import ensure_form_definitions

        auditor = get_user_model().objects.create_user("e2e-auditor", password="pass123")
        UserRole.objects.create(user=auditor, role="AUDITOR")
        administrator = get_user_model().objects.create_superuser("e2e-admin", "e2e-admin@example.test", "pass123")
        for non_creator in (self.supervisor_one, self.supervisor_two, self.receiver, auditor, administrator):
            self.client.force_login(non_creator)
            self.assertEqual(self.client.get("/actas/new/").status_code, 403)

        ensure_form_definitions()
        form_data = {
            "act_date": timezone.localdate().isoformat(),
            "act_type": "Entrega",
            "glpi_case_number": "TEST-E2E-ALL-ROLES",
            "portfolio": "Progreser2",
            "legal_custody_accepted": "on",
            "legal_accuracy_confirmed": "on",
            "legal_data_processing_accepted": "on",
        }
        for field in FormFieldDefinition.objects.filter(active=True):
            if field.required:
                form_data[f"field_{field.key}"] = "Dato completo de prueba"
        self.client.force_login(self.technician)
        with patch("actas.html_views.GlpiClient.get_case", return_value={"email": self.receiver.email}):
            response = self.client.post("/actas/new/", form_data)
        self.assertEqual(response.status_code, 302)
        acta = Acta.objects.get(glpi_case_number="TEST-E2E-ALL-ROLES")
        self.assertEqual(acta.status, "PENDING_SUPERVISOR_ONE")
        self.assertEqual(Signature.objects.get(acta=acta, signature_type="DELIVERY").signed_by, self.technician)

        self.client.force_login(self.supervisor_one)
        self.assertContains(self.client.get("/actas/review/"), acta.glpi_case_number)
        response = self.client.post("/actas/review/", {"acta_id": acta.pk, "action": "approve"})
        self.assertEqual(response.status_code, 302)
        response = self.client.post(f"/actas/{acta.public_id}/sign/", {"signature_type": "REVIEW", "signer_name": "Supervisor uno"})
        self.assertEqual(response.status_code, 302)
        acta.refresh_from_db()
        self.assertEqual(acta.status, "PENDING_SUPERVISOR_TWO")

        self.client.force_login(self.supervisor_two)
        self.assertContains(self.client.get("/actas/review/"), acta.glpi_case_number)
        response = self.client.post("/actas/review/", {"acta_id": acta.pk, "action": "approve"})
        self.assertEqual(response.status_code, 302)
        response = self.client.post(f"/actas/{acta.public_id}/sign/", {"signature_type": "FINAL_APPROVAL", "signer_name": "Supervisor dos"})
        self.assertEqual(response.status_code, 302)
        acta.refresh_from_db()
        self.assertEqual(acta.status, "PENDING_RECEIVER_UPLOAD")

        self.client.force_login(self.receiver)
        pdf = SimpleUploadedFile("acta-e2e.pdf", b"%PDF-1.4\nPrueba completa\n%%EOF", content_type="application/pdf")
        response = self.client.post(f"/actas/{acta.public_id}/receiver-upload/", {"signed_scan": pdf})
        self.assertEqual(response.status_code, 302)
        acta.refresh_from_db()
        self.assertEqual(acta.status, "COMPLETED")
        self.assertTrue(acta.completed_at)
        self.assertEqual(set(acta.signatures.filter(result="APPROVED").values_list("signature_type", flat=True)), {"DELIVERY", "REVIEW", "FINAL_APPROVAL", "RECEIVE"})

        for reviewer in (administrator, auditor):
            self.client.force_login(reviewer)
            self.assertEqual(self.client.get("/accounts/dashboard/").status_code, 200)
            self.assertEqual(self.client.get(f"/actas/{acta.public_id}/").status_code, 200)

    @override_settings(IS_TEST_ENVIRONMENT=False, GLPI_UPLOAD_ENABLED=False)
    def test_new_acta_full_flow_starts_with_receiver_and_blocks_other_roles_from_creation(self):
        from notifications.models import Notification
        from .html_views import ensure_form_definitions

        auditor = get_user_model().objects.create_user("flow-auditor", password="pass123")
        UserRole.objects.create(user=auditor, role="AUDITOR")
        administrator = get_user_model().objects.create_superuser("flow-admin", "flow-admin@example.test", "pass123")
        for non_creator in (self.supervisor_one, self.supervisor_two, self.receiver, auditor, administrator):
            self.client.force_login(non_creator)
            self.assertEqual(self.client.get("/actas/new/").status_code, 403)

        ensure_form_definitions()
        form_data = {
            "act_date": timezone.localdate().isoformat(),
            "act_type": "Entrega",
            "glpi_case_number": "TEST-E2E-ORDERED-FLOW",
            "portfolio": "Progreser2",
            "legal_custody_accepted": "on",
            "legal_accuracy_confirmed": "on",
            "legal_data_processing_accepted": "on",
        }
        for field in FormFieldDefinition.objects.filter(active=True, required=True):
            form_data[f"field_{field.key}"] = "Dato completo de prueba"
        self.client.force_login(self.technician)
        with patch("actas.html_views.GlpiClient.get_case", return_value={"email": self.receiver.email}):
            response = self.client.post("/actas/new/", form_data)
        self.assertEqual(response.status_code, 302)
        acta = Acta.objects.get(glpi_case_number="TEST-E2E-ORDERED-FLOW")
        self.assertEqual(acta.status, "PENDING_RECEIVER_SIGNATURE")
        self.assertFalse(acta.signatures.filter(result="APPROVED").exists())
        detail = self.client.get(f"/actas/{acta.public_id}/")
        self.assertContains(detail, str(acta.receiver_signature_token))

        with self.captureOnCommitCallbacks(execute=True):
            early = self.client.post(f"/actas/{acta.public_id}/sign/", {"signature_type": "DELIVERY"})
        self.assertEqual(early.status_code, 302)
        self.assertFalse(acta.signatures.filter(signature_type="DELIVERY", result="APPROVED").exists())

        receiver_url = f"/actas/receiver/sign/{acta.receiver_signature_token}/"
        self.client.logout()
        self.assertEqual(self.client.get(receiver_url).status_code, 200)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(receiver_url, {"signature_data": PNG_DATA})
        self.assertEqual(response.status_code, 200)
        acta.refresh_from_db()
        self.assertEqual(acta.status, "PENDING_TECHNICIAN_DELIVERY")
        self.assertTrue(Notification.objects.filter(acta=acta, recipient=self.technician, title="Firma del receptor registrada").exists())

        self.client.force_login(self.technician)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(f"/actas/{acta.public_id}/sign/", {"signature_type": "DELIVERY"})
        self.assertEqual(response.status_code, 302)
        acta.refresh_from_db()
        self.assertEqual(acta.status, "PENDING_SUPERVISOR_ONE")
        self.assertTrue(Notification.objects.filter(acta=acta, recipient=self.supervisor_one, title="Revisión pendiente").exists())

        self.client.force_login(self.supervisor_one)
        self.assertContains(self.client.get("/actas/review/"), acta.glpi_case_number)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(f"/actas/{acta.public_id}/sign/", {"signature_type": "REVIEW"})
        self.assertEqual(response.status_code, 302)
        acta.refresh_from_db()
        self.assertEqual(acta.status, "PENDING_SUPERVISOR_TWO")
        self.assertTrue(Notification.objects.filter(acta=acta, recipient=self.supervisor_two, title="Aprobación final pendiente").exists())

        self.client.force_login(self.supervisor_two)
        self.assertContains(self.client.get("/actas/review/"), acta.glpi_case_number)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(f"/actas/{acta.public_id}/sign/", {"signature_type": "FINAL_APPROVAL"})
        self.assertEqual(response.status_code, 302)
        acta.refresh_from_db()
        self.assertEqual(acta.status, "COMPLETED")
        self.assertTrue(acta.pdf_file)
        self.assertTrue(acta.pdf_file.read().startswith(b"%PDF-"))
        self.assertTrue(Notification.objects.filter(acta=acta, recipient=self.technician, title="Acta completada").exists())
        self.assertEqual(
            list(acta.signatures.filter(result="APPROVED").order_by("signed_at").values_list("signature_type", flat=True)),
            ["RECEIVE", "DELIVERY", "REVIEW", "FINAL_APPROVAL"],
        )

        for reviewer in (administrator, auditor):
            self.client.force_login(reviewer)
            self.assertEqual(self.client.get("/accounts/dashboard/").status_code, 200)
            self.assertEqual(self.client.get(f"/actas/{acta.public_id}/").status_code, 200)

    def test_technician_can_correct_rejected_acta_and_supervisor_can_sign_again(self):
        self.acta.status = "REJECTED_BY_SUPERVISOR_ONE"
        self.acta.rejection_step = "SUPERVISOR_ONE"
        self.acta.rejection_reason = "Corrige los datos del equipo."
        self.acta.save()
        Signature.objects.create(acta=self.acta, signature_type="REVIEW", signed_by=self.supervisor_one, signer_name="Supervisor uno", result="REJECTED", rejection_reason=self.acta.rejection_reason)
        from .html_views import ensure_form_definitions

        ensure_form_definitions()
        required_fields = FormFieldDefinition.objects.filter(active=True, required=True)
        form_data = {
            "act_date": timezone.localdate().isoformat(),
            "act_type": "Entrega",
            "glpi_case_number": self.acta.glpi_case_number,
            "portfolio": "Pruebas corregidas",
            "legal_custody_accepted": "on",
            "legal_accuracy_confirmed": "on",
            "legal_data_processing_accepted": "on",
        }
        for field in required_fields:
            form_data[f"field_{field.key}"] = "Dato corregido"
        self.client.login(username="technician", password="pass123")
        response = self.client.post(f"/actas/{self.acta.public_id}/edit/", form_data)
        self.assertEqual(response.status_code, 302)
        self.acta.refresh_from_db()
        self.assertEqual(self.acta.status, "PENDING_RECEIVER_SIGNATURE")
        self.assertEqual(self.acta.signatures.filter(result="SUPERSEDED").count(), 2)
        self.assertEqual(self.acta.rejection_reason, "")
        self.assertEqual(self.acta.receiver, self.receiver)
        self.client.logout()
        receiver_url = f"/actas/receiver/sign/{self.acta.receiver_signature_token}/"
        self.client.post(receiver_url, {"signature_data": PNG_DATA})
        self.client.force_login(self.technician)
        self.client.post(f"/actas/{self.acta.public_id}/sign/", {"signature_type": "DELIVERY"})
        self.acta.refresh_from_db()
        self.assertEqual(self.acta.status, "PENDING_SUPERVISOR_ONE")
        self.client.login(username="supervisor-one", password="pass123")
        response = self.client.post(f"/actas/{self.acta.public_id}/sign/", {
            "signature_type": "REVIEW", "signer_name": "Supervisor uno",
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Signature.objects.filter(acta=self.acta, signature_type="REVIEW", result="APPROVED").exists())


def tearDownModule():
    shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

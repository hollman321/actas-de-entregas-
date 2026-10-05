from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from .models import PilotFeedback


class ReportsAndPilotTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username="report-admin", email="report-admin@example.test", password="qa-only-password"
        )
        self.client.login(username="report-admin", password="qa-only-password")

    def test_reports_page_and_excel_export(self):
        page = self.client.get("/accounts/reports/")
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Equipos entregados por marca y modelo")
        export = self.client.get("/accounts/reports/export/xlsx/")
        self.assertEqual(export.status_code, 200)
        self.assertEqual(export["Content-Type"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.assertTrue(export.content.startswith(b"PK"))

    def test_pdf_export_renders_a_pdf_document(self):
        response = self.client.get("/accounts/reports/export/pdf/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))

    @override_settings(PILOT_MODE=True, PILOT_END_DATE="2099-01-01")
    def test_pilot_feedback_is_saved_for_authenticated_user(self):
        response = self.client.post("/accounts/pilot-feedback/", {
            "category": "SUGGESTION",
            "message": "Aclarar el paso de selección de sede.",
            "page": "/actas/new/",
        })
        self.assertEqual(response.status_code, 302)
        feedback = PilotFeedback.objects.get()
        self.assertEqual(feedback.user, self.admin)
        self.assertEqual(feedback.category, "SUGGESTION")
        self.assertEqual(feedback.page, "/actas/new/")

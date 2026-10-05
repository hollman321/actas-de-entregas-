import base64

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile

from actas.models import Acta, Signature
from audit.models import ActaEvent
from notifications.models import Notification
from .admin import UserAdmin
from .models import UserRole


PNG_DATA = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
)
class UserAdministrationTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.admin_user = self.user_model.objects.create_superuser(
            username="account-admin",
            email="account-admin@example.test",
            password="pass123",
        )
        self.user = self.user_model.objects.create_user(
            username="editable-user",
            email="old@example.test",
            password="pass123",
        )
        self.profile = UserRole.objects.create(user=self.user, role="TECHNICIAN")
        self.client.force_login(self.admin_user)

    def test_admin_can_edit_user_details_role_and_digital_signature(self):
        change_url = reverse("admin:auth_user_change", args=[self.user.pk])
        page = self.client.get(change_url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "digital_signature")

        response = self.client.post(
            change_url,
            {
                "username": self.user.username,
                "first_name": "Ada",
                "last_name": "Prueba",
                "email": "ada@example.test",
                "is_active": "on",
                "is_staff": "",
                "is_superuser": "",
                "date_joined_0": self.user.date_joined.strftime("%Y-%m-%d"),
                "date_joined_1": self.user.date_joined.strftime("%H:%M:%S"),
                "role_profile-TOTAL_FORMS": "1",
                "role_profile-INITIAL_FORMS": "1",
                "role_profile-MIN_NUM_FORMS": "0",
                "role_profile-MAX_NUM_FORMS": "1",
                "role_profile-0-id": str(self.profile.pk),
                "role_profile-0-user": str(self.user.pk),
                "role_profile-0-role": "RECEIVER",
                "role_profile-0-active": "on",
                "role_profile-0-digital_signature": SimpleUploadedFile(
                    "signature.png", PNG_DATA, content_type="image/png"
                ),
                "_save": "Save",
            },
        )

        if response.status_code == 200:
            inline_formset = response.context["inline_admin_formsets"][0].formset
            errors = {
                "user": response.context["adminform"].form.errors,
                "inline": [form.errors for form in inline_formset.forms],
                "non_form": inline_formset.non_form_errors(),
            }
        else:
            errors = None
        self.assertEqual(response.status_code, 302, errors)
        self.user.refresh_from_db()
        self.profile.refresh_from_db()
        self.assertEqual(self.user.first_name, "Ada")
        self.assertEqual(self.user.last_name, "Prueba")
        self.assertEqual(self.user.email, "ada@example.test")
        self.assertEqual(self.profile.role, "RECEIVER")
        self.assertTrue(self.profile.digital_signature.name.endswith(".png"))

    def test_admin_deactivates_user_without_deleting_related_history(self):
        acta = Acta.objects.create(
            glpi_case_number="USER-DEACTIVATION-HISTORY",
            created_by=self.user,
        )
        signature = Signature.objects.create(
            acta=acta,
            signature_type="DELIVERY",
            signed_by=self.user,
            signer_name="Usuario de prueba",
        )
        event = ActaEvent.objects.create(
            acta=acta,
            event_type="TEST",
            action="USER_HISTORY",
            actor=self.user,
        )
        notification = Notification.objects.create(
            recipient=self.user,
            title="Aviso de prueba",
            message="Notificación asociada a la cuenta.",
        )
        response = self.client.post(
            reverse("admin:auth_user_changelist"),
            {
                "action": "deactivate_selected_users",
                "_selected_action": [str(self.user.pk)],
                "index": "0",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertTrue(Acta.objects.filter(pk=acta.pk, created_by=self.user).exists())
        self.assertTrue(Signature.objects.filter(pk=signature.pk, signed_by=self.user).exists())
        self.assertTrue(ActaEvent.objects.filter(pk=event.pk, actor=self.user).exists())
        self.assertTrue(Notification.objects.filter(pk=notification.pk, recipient=self.user).exists())
        self.assertFalse(self.client.login(username=self.user.username, password="pass123"))
        self.assertFalse(
            UserRole.objects.filter(
                user=self.user,
                role="RECEIVER",
                active=True,
                user__is_active=True,
            ).exists()
        )

    def test_admin_cannot_delete_users_and_delete_action_is_not_available(self):
        user_admin = admin.site._registry[self.user_model]
        self.assertIsInstance(user_admin, UserAdmin)
        request = RequestFactory().get("/admin/auth/user/")
        request.user = self.admin_user
        self.assertFalse(user_admin.has_delete_permission(request))
        self.assertNotIn("delete_selected", user_admin.get_actions(request))
        response = self.client.get(
            reverse("admin:auth_user_delete", args=[self.user.pk])
        )
        self.assertEqual(response.status_code, 403)

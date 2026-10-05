from django.conf import settings
from django.db import models
from django.core.validators import FileExtensionValidator
from django.core.exceptions import ValidationError


def validate_signature_size(upload):
    if upload.size > 1024 * 1024:
        raise ValidationError("La firma PNG no puede superar 1 MB.")


class UserRole(models.Model):
    objects = models.Manager()

    ROLE_CHOICES = [("ADMIN", "Administrador"), ("TECHNICIAN", "Tecnico"), ("SUPERVISOR_ONE", "Supervisor uno"), ("SUPERVISOR_TWO", "Supervisor dos"), ("RECEIVER", "Receptor del activo"), ("AUDITOR", "Auditor")]
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="role_profile")
    role = models.CharField(max_length=30, choices=ROLE_CHOICES)
    active = models.BooleanField(default=True)
    digital_signature = models.ImageField(upload_to="supervisor-signatures/", blank=True, null=True, validators=[FileExtensionValidator(["png"]), validate_signature_size])

    def __str__(self):
        return f"{self.user} - {self.role}"


class WorkflowConfig(models.Model):
    """Global approvers used for every new acta; editable only in Django admin."""
    objects = models.Manager()
    supervisor_one = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="workflow_supervisor_one")
    supervisor_two = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="workflow_supervisor_two")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="workflow_config_updates")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Configuración de supervisores"
        verbose_name_plural = "Configuración de supervisores"

    def __str__(self):
        return "Supervisores globales de actas"

    def clean(self):
        super().clean()
        for field, role in (("supervisor_one", "SUPERVISOR_ONE"), ("supervisor_two", "SUPERVISOR_TWO")):
            user = getattr(self, field)
            if user and not UserRole.objects.filter(user=user, role=role, active=True, user__is_active=True).exists():
                raise ValidationError({field: "Selecciona un usuario activo con el rol de supervisor correspondiente."})
        if self.supervisor_one and self.supervisor_one == self.supervisor_two:
            raise ValidationError("Los dos roles de supervisor deben pertenecer a personas distintas.")

    @classmethod
    def get_solo(cls):
        config, _ = cls.objects.get_or_create(pk=1)
        updates = {}
        for field, role, username in (
            ("supervisor_one", "SUPERVISOR_ONE", "carlos"),
            ("supervisor_two", "SUPERVISOR_TWO", "jaime"),
        ):
            if getattr(config, f"{field}_id") is None:
                profile = UserRole.objects.filter(
                    role=role, active=True, user__is_active=True,
                    user__username__iexact=username,
                ).select_related("user").first()
                if profile:
                    updates[field] = profile.user
        if updates:
            for field, user in updates.items():
                setattr(config, field, user)
            config.save(update_fields=[*updates, "updated_at"])
        return config

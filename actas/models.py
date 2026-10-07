import uuid
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.core.exceptions import ValidationError


class Site(models.Model):
    objects = models.Manager()

    code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=120)
    active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.code} - {self.name}"


class FormFieldDefinition(models.Model):
    objects = models.Manager()

    FIELD_TYPES = [("text", "Texto"), ("number", "Numero"), ("date", "Fecha"), ("choice", "Lista"), ("boolean", "Si/No")]
    key = models.SlugField(max_length=80, unique=True)
    label = models.CharField(max_length=160)
    section = models.CharField(max_length=80)
    field_type = models.CharField(max_length=20, choices=FIELD_TYPES, default="text")
    required = models.BooleanField(default=False)
    editable = models.BooleanField(default=True)
    options = models.JSONField(default=list, blank=True)
    version = models.PositiveIntegerField(default=1)
    sort_order = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["section", "sort_order"]


class PortfolioCatalog(models.Model):
    """Portfolio defaults for the Usuarios block, maintained by administrators."""
    objects = models.Manager()
    name = models.CharField(max_length=120, unique=True)
    defaults = models.JSONField(default=dict, blank=True, help_text="Valores por etiqueta de campo, por ejemplo: Acceso a HelpDesk GLPI: true.")
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Portafolio"
        verbose_name_plural = "Catálogo de portafolios"

    def __str__(self):
        return str(self.name)

    def clean(self):
        super().clean()
        if not isinstance(self.defaults, dict):
            raise ValidationError({"defaults": "Los valores del portafolio deben ser un objeto JSON de etiqueta a valor."})


class CampaignCatalog(models.Model):
    objects = models.Manager()
    name = models.CharField(max_length=120, unique=True)
    portfolio = models.ForeignKey(
        PortfolioCatalog,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="campaigns",
    )
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Campaña"
        verbose_name_plural = "Catálogo de campañas"

    def __str__(self):
        return str(self.name)


class Acta(models.Model):
    objects = models.Manager()

    STATUS = [
        ("DRAFT", "Borrador"), ("RECEIVER_SIGNED", "Firma física del receptor registrada"),
        ("PENDING_RECEIVER_SIGNATURE", "Pendiente firma del receptor"),
        ("PENDING_TECHNICIAN_DELIVERY", "Pendiente firma de Entrega del técnico"),
        ("DELIVERY_SIGNED", "Entrega firmada"), ("PENDING_SUPERVISOR_ONE", "Pendiente Supervisor uno"),
        ("REJECTED_BY_SUPERVISOR_ONE", "Rechazada por Supervisor uno"),
        ("PENDING_SUPERVISOR_TWO", "Pendiente Supervisor dos"),
        ("REJECTED_BY_SUPERVISOR_TWO", "Rechazada por Supervisor dos"),
        ("PENDING_RECEIVER_UPLOAD", "Pendiente de escaneo firmado por el receptor"),
        ("COMPLETED", "Completada"), ("GLPI_UPLOAD_PENDING", "Pendiente de GLPI"),
        ("GLPI_UPLOADED", "Archivada en GLPI"), ("GLPI_UPLOAD_FAILED", "Error en GLPI"),
    ]
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    receiver_signature_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    form_version = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=40, choices=STATUS, default="DRAFT")
    site = models.ForeignKey(Site, null=True, blank=True, on_delete=models.PROTECT)
    act_type = models.CharField(max_length=80, blank=True)
    act_date = models.DateField(null=True, blank=True)
    glpi_case_number = models.CharField(max_length=80, unique=True)
    portfolio = models.CharField(max_length=120, blank=True)
    campaign = models.ForeignKey(
        CampaignCatalog,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="actas",
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="actas_created")
    assigned_technician = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="actas_technician")
    receiver = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="actas_receiver")
    supervisor_one = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="actas_supervisor_one")
    supervisor_two = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="actas_supervisor_two")
    rejection_reason = models.TextField(blank=True)
    rejection_step = models.CharField(max_length=40, blank=True)
    legal_custody_accepted = models.BooleanField(default=False)
    legal_accuracy_confirmed = models.BooleanField(default=False)
    legal_data_processing_accepted = models.BooleanField(default=False)
    legal_accepted_at = models.DateTimeField(null=True, blank=True)
    legal_acceptance_ip = models.GenericIPAddressField(null=True, blank=True)
    due_at = models.DateTimeField(null=True, blank=True)
    pdf_file = models.FileField(upload_to="actas/%Y/%m/", null=True, blank=True)
    glpi_upload_status = models.CharField(max_length=30, default="PENDING")
    glpi_uploaded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)


class ActaFieldValue(models.Model):
    objects = models.Manager()

    acta = models.ForeignKey(Acta, on_delete=models.CASCADE, related_name="field_values")
    definition = models.ForeignKey(FormFieldDefinition, on_delete=models.PROTECT)
    value = models.JSONField(default=dict, blank=True)
    source = models.CharField(max_length=20, default="MANUAL")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["acta", "definition"], name="unique_acta_field")]


class Signature(models.Model):
    objects = models.Manager()

    TYPES = [("RECEIVE", "Recibe"), ("DELIVERY", "Entrega"), ("REVIEW", "Reviso"), ("FINAL_APPROVAL", "Aprobo")]
    acta = models.ForeignKey(Acta, on_delete=models.CASCADE, related_name="signatures")
    signature_type = models.CharField(max_length=20, choices=TYPES)
    signed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT)
    signer_name = models.CharField(max_length=160)
    signer_role = models.CharField(max_length=80, blank=True)
    signer_document = models.CharField(max_length=40, blank=True)
    signature_image = models.ImageField(upload_to="signatures/%Y/%m/", null=True, blank=True)
    signature_hash = models.CharField(max_length=128, blank=True)
    signed_at = models.DateTimeField(auto_now_add=True)
    result = models.CharField(max_length=20, blank=True)
    rejection_reason = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    method = models.CharField(max_length=20, default="DESKTOP")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["acta", "signature_type"], condition=Q(result="APPROVED"), name="unique_approved_acta_signature")]

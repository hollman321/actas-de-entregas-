import uuid

from django.db import migrations, models


def populate_receiver_signature_tokens(apps, schema_editor):
    Acta = apps.get_model("actas", "Acta")
    for acta in Acta.objects.filter(receiver_signature_token__isnull=True).iterator():
        Acta.objects.filter(pk=acta.pk).update(receiver_signature_token=uuid.uuid4())


class Migration(migrations.Migration):

    dependencies = [
        ("actas", "0008_campaigncatalog_portfolio"),
    ]

    operations = [
        migrations.AddField(
            model_name="acta",
            name="receiver_signature_token",
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.RunPython(populate_receiver_signature_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="acta",
            name="receiver_signature_token",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AlterField(
            model_name="acta",
            name="status",
            field=models.CharField(
                choices=[
                    ("DRAFT", "Borrador"),
                    ("RECEIVER_SIGNED", "Firma física del receptor registrada"),
                    ("PENDING_RECEIVER_SIGNATURE", "Pendiente firma del receptor"),
                    ("PENDING_TECHNICIAN_DELIVERY", "Pendiente firma de Entrega del técnico"),
                    ("DELIVERY_SIGNED", "Entrega firmada"),
                    ("PENDING_SUPERVISOR_ONE", "Pendiente Supervisor uno"),
                    ("REJECTED_BY_SUPERVISOR_ONE", "Rechazada por Supervisor uno"),
                    ("PENDING_SUPERVISOR_TWO", "Pendiente Supervisor dos"),
                    ("REJECTED_BY_SUPERVISOR_TWO", "Rechazada por Supervisor dos"),
                    ("PENDING_RECEIVER_UPLOAD", "Pendiente de escaneo firmado por el receptor"),
                    ("COMPLETED", "Completada"),
                    ("GLPI_UPLOAD_PENDING", "Pendiente de GLPI"),
                    ("GLPI_UPLOADED", "Archivada en GLPI"),
                    ("GLPI_UPLOAD_FAILED", "Error en GLPI"),
                ],
                default="DRAFT",
                max_length=40,
            ),
        ),
    ]

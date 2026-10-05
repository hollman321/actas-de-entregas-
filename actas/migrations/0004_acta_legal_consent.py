from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("actas", "0003_allow_signature_retries_after_rejection"),
    ]

    operations = [
        migrations.AddField(
            model_name="acta",
            name="legal_custody_accepted",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="acta",
            name="legal_accuracy_confirmed",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="acta",
            name="legal_data_processing_accepted",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="acta",
            name="legal_accepted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="acta",
            name="legal_acceptance_ip",
            field=models.GenericIPAddressField(blank=True, null=True),
        ),
    ]

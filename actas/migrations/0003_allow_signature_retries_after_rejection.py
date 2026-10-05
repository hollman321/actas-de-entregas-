from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [("actas", "0002_signature_rejection_reason_signature_result_and_more")]

    operations = [
        migrations.RemoveConstraint(model_name="signature", name="unique_acta_signature"),
        migrations.AddConstraint(
            model_name="signature",
            constraint=models.UniqueConstraint(
                fields=("acta", "signature_type"),
                condition=Q(result="APPROVED"),
                name="unique_approved_acta_signature",
            ),
        ),
    ]

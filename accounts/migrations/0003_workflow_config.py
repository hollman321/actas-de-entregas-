import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def seed_default_supervisors(apps, schema_editor):
    UserRole = apps.get_model("accounts", "UserRole")
    WorkflowConfig = apps.get_model("accounts", "WorkflowConfig")
    config, _ = WorkflowConfig.objects.using(schema_editor.connection.alias).get_or_create(pk=1)
    for field, username, role in (("supervisor_one_id", "carlos", "SUPERVISOR_ONE"), ("supervisor_two_id", "jaime", "SUPERVISOR_TWO")):
        profile = UserRole.objects.using(schema_editor.connection.alias).filter(
            role=role, active=True, user__is_active=True, user__username__iexact=username
        ).first()
        if profile:
            setattr(config, field, profile.user_id)
    config.save(using=schema_editor.connection.alias)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_userrole_digital_signature_alter_userrole_role"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="WorkflowConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("supervisor_one", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="workflow_supervisor_one", to=settings.AUTH_USER_MODEL)),
                ("supervisor_two", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="workflow_supervisor_two", to=settings.AUTH_USER_MODEL)),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="workflow_config_updates", to=settings.AUTH_USER_MODEL)),
            ],
            options={"verbose_name": "Configuración de supervisores", "verbose_name_plural": "Configuración de supervisores"},
        ),
        migrations.RunPython(seed_default_supervisors, migrations.RunPython.noop),
    ]

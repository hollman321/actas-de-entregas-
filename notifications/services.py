import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from accounts.models import UserRole
from .models import Notification

logger = logging.getLogger(__name__)


SIGNATURE_MESSAGES = {
    "RECEIVE": ("Firma del receptor registrada", "El receptor firm\u00f3 el acta. El t\u00e9cnico debe completar la firma de Entrega.", "WARNING"),
    "DELIVERY": ("Revisi\u00f3n pendiente", "El t\u00e9cnico firm\u00f3 la Entrega. Carlos, Supervisor uno, debe revisar el acta.", "WARNING"),
    "REVIEW": ("Aprobaci\u00f3n final pendiente", "Carlos, Supervisor uno, revis\u00f3 el acta. Jaime, Supervisor dos, debe aprobarla.", "WARNING"),
    "FINAL_APPROVAL": ("Acta completada", "Jaime, Supervisor dos, aprob\u00f3 el acta. El PDF final est\u00e1 disponible.", "SUCCESS"),
}


def _role_user(role, exclude=None):
    users = UserRole.objects.filter(role=role, active=True).select_related("user")
    if exclude:
        users = users.exclude(user=exclude)
    return users.first().user if users.exists() else None


def next_recipient(acta, signature_type):
    if signature_type == "RECEIVE":
        return acta.assigned_technician or acta.created_by
    if signature_type == "DELIVERY":
        return acta.supervisor_one or _role_user("SUPERVISOR_ONE")
    if signature_type == "REVIEW":
        return acta.supervisor_two or _role_user("SUPERVISOR_TWO")
    if signature_type == "FINAL_APPROVAL":
        return acta.assigned_technician or acta.created_by
    return acta.created_by


def notify_signature_saved(acta, signature, actor=None):
    recipient = next_recipient(acta, signature.signature_type)
    if signature.result == "REJECTED":
        recipient = acta.assigned_technician or acta.created_by
    if recipient is None:
        logger.warning("No se encontró destinatario para acta=%s firma=%s", acta.public_id, signature.signature_type)
        return

    title, message, level = SIGNATURE_MESSAGES[signature.signature_type]
    if signature.result == "REJECTED":
        title = "Acta rechazada"
        message = f"El acta fue rechazada por {signature.signer_name}. Motivo: {signature.rejection_reason}"
        level = "ERROR"
    try:
        notification = Notification.objects.create(recipient=recipient, acta=acta, title=title, message=message, level=level)
    except Exception:
        logger.exception("Error creando notificación interna recipient=%s acta=%s firma=%s", recipient.username, acta.public_id, signature.signature_type)
        return
    logger.info("Notificación interna creada id=%s recipient=%s acta=%s firma=%s", notification.pk, recipient.username, acta.public_id, signature.signature_type)

    if settings.IS_TEST_ENVIRONMENT or not recipient.email:
        logger.warning("Destinatario sin correo recipient=%s acta=%s", recipient.username, acta.public_id)
        return

    try:
        send_mail(
            f"{title}: caso GLPI {acta.glpi_case_number}",
            message,
            settings.DEFAULT_FROM_EMAIL,
            [recipient.email],
            fail_silently=False,
        )
        logger.info("Correo de firma enviado recipient=%s acta=%s firma=%s", recipient.email, acta.public_id, signature.signature_type)
    except Exception:
        logger.exception("Error enviando correo recipient=%s acta=%s firma=%s", recipient.email, acta.public_id, signature.signature_type)


def schedule_signature_notification(acta, signature, actor=None):
    transaction.on_commit(lambda: notify_signature_saved(acta, signature, actor=actor))


def notify_pending(recipient, acta):
    subject = f"Acta pendiente: caso GLPI {acta.glpi_case_number}"
    message = "Tiene un acta pendiente de revisión en Automatizacion Actas de Entrega."
    logger.info("Intentando enviar notificación pendiente recipient=%s acta=%s", recipient.email, acta.public_id)
    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [recipient.email], fail_silently=False)

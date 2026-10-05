from django.db import IntegrityError, transaction
import hashlib
from django.core.files.base import ContentFile
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import Acta, FormFieldDefinition, Signature
from .serializers import ActaSerializer, FormFieldDefinitionSerializer, SignatureSerializer
from notifications.services import schedule_signature_notification
from accounts.permissions import active_role, visible_actas


class ActaViewSet(viewsets.ModelViewSet):
    queryset = Acta.objects.prefetch_related("signatures", "field_values").all()
    serializer_class = ActaSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "public_id"

    def get_queryset(self):
        return visible_actas(super().get_queryset(), self.request.user)

    def create(self, request, *args, **kwargs):
        if active_role(request.user) != "TECHNICIAN":
            return Response({"detail": "Solo los t\u00e9cnicos pueden crear actas."}, status=status.HTTP_403_FORBIDDEN)
        return Response({"detail": "Usa el formulario web para registrar todos los datos, aceptaciones, receptor y firma fija del acta."}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

    def update(self, request, *args, **kwargs):
        if active_role(request.user) != "ADMIN":
            return Response({"detail": "Solo un administrador puede modificar actas."}, status=status.HTTP_403_FORBIDDEN)
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        if active_role(request.user) != "ADMIN":
            return Response({"detail": "Solo un administrador puede modificar actas."}, status=status.HTTP_403_FORBIDDEN)
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if active_role(request.user) != "ADMIN":
            return Response({"detail": "Solo un administrador puede eliminar actas."}, status=status.HTTP_403_FORBIDDEN)
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="receive/sign")
    def sign_receive(self, request, public_id=None):
        return Response({"detail": "El receptor debe cargar el escaneo con su firma física después de la aprobación."}, status=status.HTTP_410_GONE)

    @action(detail=True, methods=["post"], url_path="delivery/sign")
    def sign_delivery(self, request, public_id=None):
        return Response({"detail": "La firma física corresponde únicamente al receptor del activo."}, status=status.HTTP_410_GONE)

    @action(detail=True, methods=["post"], url_path="review/approve")
    def review_approve(self, request, public_id=None):
        return self._sign(request, self.get_object(), "REVIEW", "PENDING_SUPERVISOR_TWO", "PENDING_SUPERVISOR_ONE")

    @action(detail=True, methods=["post"], url_path="review/reject")
    def review_reject(self, request, public_id=None):
        return self._reject(request, self.get_object(), "REJECTED_BY_SUPERVISOR_ONE", "SUPERVISOR_ONE")

    @action(detail=True, methods=["post"], url_path="final-approval/approve")
    def final_approve(self, request, public_id=None):
        return self._sign(request, self.get_object(), "FINAL_APPROVAL", "PENDING_RECEIVER_UPLOAD", "PENDING_SUPERVISOR_TWO")

    @action(detail=True, methods=["post"], url_path="final-approval/reject")
    def final_reject(self, request, public_id=None):
        return self._reject(request, self.get_object(), "REJECTED_BY_SUPERVISOR_TWO", "SUPERVISOR_TWO")

    def _sign(self, request, acta, signature_type, next_status, required_status):
        role = active_role(request.user)
        allowed_roles = {"REVIEW": {"SUPERVISOR_ONE"}, "FINAL_APPROVAL": {"SUPERVISOR_TWO"}}
        if role not in allowed_roles.get(signature_type, set()):
            return Response({"detail": "Tu rol no puede registrar esta firma."}, status=status.HTTP_403_FORBIDDEN)
        expected_users = {"RECEIVE": acta.receiver, "DELIVERY": acta.assigned_technician, "REVIEW": acta.supervisor_one, "FINAL_APPROVAL": acta.supervisor_two}
        expected_user = expected_users.get(signature_type)
        if expected_user is None or request.user.pk != expected_user.pk:
            return Response({"detail": "Permiso denegado: tu sesión no corresponde al usuario asignado para esta firma."}, status=status.HTTP_403_FORBIDDEN)
        existing_types = set(acta.signatures.filter(result="APPROVED").values_list("signature_type", flat=True))
        required_signatures = {"REVIEW": {"DELIVERY"}, "FINAL_APPROVAL": {"DELIVERY", "REVIEW"}}
        if signature_type in required_signatures and not required_signatures[signature_type].issubset(existing_types):
            return Response({"detail": "Faltan firmas anteriores para esta etapa."}, status=status.HTTP_409_CONFLICT)
        if required_status and acta.status != required_status:
            return Response({"detail": "La etapa anterior no esta completa."}, status=status.HTTP_409_CONFLICT)
        signer_name = request.data.get("signer_name") or request.user.get_full_name() or request.user.username
        is_supervisor_approval = signature_type in {"REVIEW", "FINAL_APPROVAL"}
        if is_supervisor_approval:
            profile = getattr(request.user, "role_profile", None)
            if not profile or not profile.digital_signature:
                return Response({"detail": "El supervisor no tiene una firma digital registrada."}, status=status.HTTP_400_BAD_REQUEST)
            profile.digital_signature.open("rb")
            signature_bytes = profile.digital_signature.read()
            profile.digital_signature.close()
            if not signature_bytes.startswith(b"\x89PNG\r\n\x1a\n") or len(signature_bytes) > 1024 * 1024:
                return Response({"detail": "La firma digital registrada no es un PNG válido o supera 1 MB."}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({"detail": "Solo se admiten firmas PNG fijas."}, status=status.HTTP_410_GONE)
        try:
            with transaction.atomic():
                signature = Signature.objects.create(acta=acta, signature_type=signature_type, signed_by=request.user, signer_name=signer_name, signer_role=getattr(getattr(request.user, "role_profile", None), "get_role_display", lambda: "")(), signer_document=request.data.get("signer_document", ""), signature_hash=hashlib.sha256(signature_bytes).hexdigest(), method="DIGITAL_PNG" if is_supervisor_approval else request.data.get("method", "DESKTOP"), result="APPROVED", ip_address=request.META.get("REMOTE_ADDR", ""), user_agent=request.META.get("HTTP_USER_AGENT", ""))
                signature.signature_image.save(f"signature-{signature.pk}.png", ContentFile(signature_bytes), save=True)
                previous_status = acta.status
                acta.status = next_status
                acta.save(update_fields=["status", "updated_at"])
                from audit.models import ActaEvent
                ActaEvent.objects.create(acta=acta, event_type="SIGNATURE", action=f"{signature_type}_APPROVED", actor=request.user, from_status=previous_status, to_status=next_status, ip_address=request.META.get("REMOTE_ADDR", ""))
                schedule_signature_notification(acta, signature, actor=request.user)
        except IntegrityError:
            return Response({"detail": "Esta firma ya existe."}, status=status.HTTP_409_CONFLICT)
        return Response(ActaSerializer(acta).data)

    def _reject(self, request, acta, next_status, step):
        reason = (request.data.get("reason") or "").strip()
        if not reason:
            return Response({"detail": "El motivo de rechazo es obligatorio."}, status=status.HTTP_400_BAD_REQUEST)
        signature_type = "FINAL_APPROVAL" if step == "SUPERVISOR_TWO" else "REVIEW"
        role = active_role(request.user)
        expected_role = "SUPERVISOR_TWO" if step == "SUPERVISOR_TWO" else "SUPERVISOR_ONE"
        if role not in {expected_role, "ADMIN"}:
            return Response({"detail": "Tu rol no puede rechazar esta acta."}, status=status.HTTP_403_FORBIDDEN)
        valid_statuses = {"SUPERVISOR_ONE": {"PENDING_SUPERVISOR_ONE"}, "SUPERVISOR_TWO": {"PENDING_SUPERVISOR_TWO"}}
        expected_user = acta.supervisor_two if step == "SUPERVISOR_TWO" else acta.supervisor_one
        if acta.status not in valid_statuses[step]:
            return Response({"detail": "Esta acta no está pendiente de revisión en esa etapa."}, status=status.HTTP_409_CONFLICT)
        if role != "ADMIN" and (expected_user is None or expected_user.pk != request.user.pk):
            return Response({"detail": "El acta no está asignada a tu usuario."}, status=status.HTTP_403_FORBIDDEN)
        required = set()
        if step == "SUPERVISOR_TWO":
            required.add("REVIEW")
        approved_types = set(acta.signatures.filter(result="APPROVED").values_list("signature_type", flat=True))
        if not required.issubset(approved_types):
            return Response({"detail": "Faltan firmas aprobadas de etapas anteriores."}, status=status.HTTP_409_CONFLICT)
        profile = getattr(request.user, "role_profile", None)
        if not profile or not profile.digital_signature:
            return Response({"detail": "Registra tu firma PNG fija antes de rechazar actas."}, status=status.HTTP_400_BAD_REQUEST)
        profile.digital_signature.open("rb")
        signature_bytes = profile.digital_signature.read()
        profile.digital_signature.close()
        if not signature_bytes.startswith(b"\x89PNG\r\n\x1a\n") or len(signature_bytes) > 1024 * 1024:
            return Response({"detail": "La firma PNG registrada no es v\u00e1lida o supera 1 MB."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            with transaction.atomic():
                signature = Signature.objects.create(acta=acta, signature_type=signature_type, signed_by=request.user, signer_name=request.user.get_full_name() or request.user.username, signer_role=getattr(getattr(request.user, "role_profile", None), "get_role_display", lambda: "")(), signature_hash=hashlib.sha256(signature_bytes).hexdigest(), result="REJECTED", rejection_reason=reason, method="DIGITAL_PNG", ip_address=request.META.get("REMOTE_ADDR", ""))
                signature.signature_image.save(f"signature-rejected-{signature.pk}.png", ContentFile(signature_bytes), save=True)
                previous_status = acta.status
                acta.status = next_status
                acta.rejection_step = step
                acta.rejection_reason = reason
                acta.save(update_fields=["status", "rejection_step", "rejection_reason", "updated_at"])
                from audit.models import ActaEvent
                ActaEvent.objects.create(acta=acta, event_type="REJECTION", action=f"{signature_type}_REJECTED", actor=request.user, from_status=previous_status, to_status=next_status, reason=reason, ip_address=request.META.get("REMOTE_ADDR", ""))
                schedule_signature_notification(acta, signature, actor=request.user)
        except IntegrityError:
            return Response({"detail": "Esta firma ya existe."}, status=status.HTTP_409_CONFLICT)
        return Response(ActaSerializer(acta).data)


class FormFieldDefinitionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = FormFieldDefinition.objects.filter(active=True)
    serializer_class = FormFieldDefinitionSerializer
    permission_classes = [IsAuthenticated]

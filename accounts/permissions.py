from django.http import Http404


def active_role(user):
    if not user.is_authenticated or not user.is_active:
        return ""
    if user.is_superuser:
        return "ADMIN"
    profile = getattr(user, "role_profile", None)
    if not profile or not profile.active:
        return ""
    return profile.role


def visible_actas(queryset, user):
    role = active_role(user)
    if role in {"ADMIN", "AUDITOR"}:
        return queryset
    if role == "TECHNICIAN":
        return queryset.filter(assigned_technician=user)
    if role == "SUPERVISOR_ONE":
        return queryset.filter(supervisor_one=user)
    if role == "SUPERVISOR_TWO":
        return queryset.filter(supervisor_two=user)
    if role == "RECEIVER":
        return queryset.filter(receiver=user)
    return queryset.none()


def get_visible_acta_or_404(public_id, user):
    from actas.models import Acta

    acta = visible_actas(Acta.objects.all(), user).filter(public_id=public_id).first()
    if acta is None:
        raise Http404
    return acta


def get_role_display(user):
    role = active_role(user)
    if role == "ADMIN" and user.is_superuser:
        return "Administrador"
    profile = getattr(user, "role_profile", None)
    return profile.get_role_display() if profile and profile.active else ""

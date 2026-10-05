from datetime import date

from django.conf import settings
from accounts.permissions import active_role

from .models import Notification


def user_notifications(request):
    notifications = []
    if request.user.is_authenticated:
        rows = Notification.objects.filter(recipient=request.user).select_related("acta")[:8]
        notifications = [{
            "title": item.title,
            "description": item.message,
            "time": item.created_at.strftime("%d/%m/%Y %H:%M"),
            "type": item.level.lower(),
        } for item in rows]

    pilot_active = settings.PILOT_MODE and bool(settings.PILOT_END_DATE)
    if pilot_active:
        try:
            pilot_active = date.fromisoformat(settings.PILOT_END_DATE) >= date.today()
        except ValueError:
            pilot_active = False
    return {
        "notifications": notifications,
        "is_test_environment": settings.IS_TEST_ENVIRONMENT,
        "pilot_active": pilot_active,
        "current_role": active_role(request.user),
    }

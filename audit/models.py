from django.conf import settings
from django.db import models
from actas.models import Acta


class ActaEvent(models.Model):
    objects = models.Manager()

    acta = models.ForeignKey(Acta, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=60)
    action = models.CharField(max_length=60)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)
    from_status = models.CharField(max_length=40, blank=True)
    to_status = models.CharField(max_length=40, blank=True)
    reason = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

from django.conf import settings
from django.db import models


class Notification(models.Model):
    LEVELS = [("INFO", "Información"), ("SUCCESS", "Éxito"), ("WARNING", "Advertencia"), ("ERROR", "Error")]
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications_received")
    acta = models.ForeignKey("actas.Acta", null=True, blank=True, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=180)
    message = models.TextField()
    level = models.CharField(max_length=20, choices=LEVELS, default="INFO")
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
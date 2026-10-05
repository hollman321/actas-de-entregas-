from django.conf import settings
from django.db import models


class PilotFeedback(models.Model):
    CATEGORIES = [("ISSUE", "Problema"), ("SUGGESTION", "Sugerencia"), ("QUESTION", "Duda")]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="pilot_feedback")
    category = models.CharField(max_length=20, choices=CATEGORIES)
    message = models.TextField(max_length=5000)
    page = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_category_display()} de {self.user} ({self.created_at:%Y-%m-%d})"

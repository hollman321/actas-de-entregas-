from django.contrib import admin
from .models import PilotFeedback


@admin.register(PilotFeedback)
class PilotFeedbackAdmin(admin.ModelAdmin):
    list_display = ("created_at", "category", "user", "reviewed")
    list_filter = ("category", "reviewed", "created_at")
    search_fields = ("user__username", "message")
    readonly_fields = ("user", "category", "message", "page", "created_at")

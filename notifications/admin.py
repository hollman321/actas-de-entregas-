from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "recipient", "acta", "level", "created_at", "read_at")
    list_filter = ("level", "created_at")
    search_fields = ("title", "message", "recipient__username")

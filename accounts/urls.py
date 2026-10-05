from django.urls import path
from . import views

app_name = "accounts"

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("notifications/", views.notifications, name="notifications"),
    path("reports/", views.reports, name="reports"),
    path("reports/export/<str:export_format>/", views.reports_export, name="reports-export"),
    path("pilot-feedback/", views.pilot_feedback, name="pilot-feedback"),
    path("supervisor-signature/", views.supervisor_signature, name="supervisor-signature"),
]

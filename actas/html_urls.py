from django.urls import path
from . import html_views

urlpatterns = [
    path("", html_views.acta_list, name="html-acta-list"),
    path("new/", html_views.acta_create, name="html-acta-create"),
    path("preview-draft/", html_views.acta_preview_draft, name="html-acta-preview-draft"),
    path("<uuid:public_id>/edit/", html_views.acta_edit, name="html-acta-edit"),
    path("glpi/autocomplete/", html_views.glpi_autocomplete, name="html-glpi-autocomplete"),
    path("portfolios/autocomplete/", html_views.portfolio_autocomplete, name="html-portfolio-autocomplete"),
    path("review/", html_views.acta_review, name="html-acta-review"),
    path("<uuid:public_id>/sign/", html_views.acta_sign, name="html-acta-sign"),
    path("<uuid:public_id>/preview/", html_views.acta_preview, name="html-acta-preview"),
    path("<uuid:public_id>/export/xlsx/", html_views.acta_export_xlsx, name="html-acta-export-xlsx"),
    path("<uuid:public_id>/receiver-upload/", html_views.acta_receiver_upload, name="html-acta-receiver-upload"),
    path("<uuid:public_id>/glpi-retry/", html_views.acta_glpi_retry, name="html-acta-glpi-retry"),
    path("<uuid:public_id>/", html_views.acta_detail, name="html-acta-detail"),
]

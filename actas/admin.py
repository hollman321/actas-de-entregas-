from django.contrib import admin
from .models import Acta, ActaFieldValue, CampaignCatalog, FormFieldDefinition, PortfolioCatalog, Signature, Site

admin.site.register([Acta, ActaFieldValue, FormFieldDefinition, Signature, Site])


@admin.register(CampaignCatalog)
class CampaignCatalogAdmin(admin.ModelAdmin):
    list_display = ("name", "active")
    list_filter = ("active",)
    search_fields = ("name",)


@admin.register(PortfolioCatalog)
class PortfolioCatalogAdmin(admin.ModelAdmin):
    list_display = ("name", "active")
    list_filter = ("active",)
    search_fields = ("name",)

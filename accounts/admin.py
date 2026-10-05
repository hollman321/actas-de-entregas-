from django.contrib import admin
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import UserRole, WorkflowConfig


class UserRoleInline(admin.StackedInline):
    model = UserRole
    can_delete = False
    extra = 0
    max_num = 1
    fields = ("role", "active", "digital_signature")


@admin.action(description="Desactivar usuarios seleccionados")
def deactivate_selected_users(modeladmin, request, queryset):
    selected = queryset.exclude(pk=request.user.pk)
    updated = selected.filter(is_active=True).update(is_active=False)
    skipped_self = queryset.filter(pk=request.user.pk).exists()
    if updated:
        modeladmin.message_user(
            request,
            _("%(count)s usuario(s) desactivado(s). Sus actas e historial se conservaron.")
            % {"count": updated},
            messages.SUCCESS,
        )
    if skipped_self:
        modeladmin.message_user(
            request,
            _("No puedes desactivar tu propia cuenta desde esta acción."),
            messages.WARNING,
        )


@admin.action(description="Reactivar usuarios seleccionados")
def reactivate_selected_users(modeladmin, request, queryset):
    updated = queryset.filter(is_active=False).update(is_active=True)
    modeladmin.message_user(
        request,
        _("%(count)s usuario(s) reactivado(s).") % {"count": updated},
        messages.SUCCESS,
    )


class UserAdmin(DjangoUserAdmin):
    inlines = (UserRoleInline,)
    actions = (deactivate_selected_users, reactivate_selected_users)

    def has_delete_permission(self, request, obj=None):
        return False


User = get_user_model()
admin.site.unregister(User)
admin.site.register(User, UserAdmin)
admin.site.register(UserRole)


@admin.register(WorkflowConfig)
class WorkflowConfigAdmin(admin.ModelAdmin):
    fields = ("supervisor_one", "supervisor_two", "updated_by", "updated_at")
    readonly_fields = ("updated_by", "updated_at")

    def has_add_permission(self, request):
        return not WorkflowConfig.objects.exists() and super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user
        obj.full_clean()
        super().save_model(request, obj, form, change)

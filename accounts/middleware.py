from urllib.parse import urlencode

from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.urls import reverse

from .permissions import active_role


class AdminRoleMiddleware:
    """Restrict Django's administrative site to active application administrators."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/admin/") and request.user.is_authenticated and active_role(request.user) != "ADMIN":
            if request.user.is_staff:
                return HttpResponseForbidden("Solo un administrador activo puede acceder a esta sección.")
            admin_login = reverse("admin:login")
            if request.path != admin_login:
                query = urlencode({"next": request.get_full_path()})
                return redirect(f"{admin_login}?{query}")
        return self.get_response(request)

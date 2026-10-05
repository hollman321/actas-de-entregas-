from django.contrib import admin
from django.urls import include, path
from django.contrib.auth import views as auth_views
from django.views.generic.base import RedirectView
from django.conf import settings
from django.conf.urls.static import static
from actas.html_views import private_media

urlpatterns = [
    path("", RedirectView.as_view(url="/accounts/dashboard/", permanent=False), name="home"),
    path("admin/", admin.site.urls),
    path("login/", auth_views.LoginView.as_view(template_name="registration/login.html", next_page="/accounts/dashboard/"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(next_page="/login/"), name="logout"),
    path("accounts/", include("accounts.urls")),
    path("actas/", include("actas.html_urls")),
    path("api/actas/", include("actas.urls")),
    path("media/<path:media_path>", private_media, name="private-media"),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

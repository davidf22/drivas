from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    # Django admin
    path("admin/", admin.site.urls),
    # Auth (login / logout / signup)
    path("accounts/login/", auth_views.LoginView.as_view(template_name="messaging/login.html"), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(next_page="/accounts/login/"), name="logout"),
    path("accounts/", include("accounts.urls")),
    # Chat platform
    path("chat/", include("messaging.urls")),
    # REST API
    path("api/jobs/", include("jobs.urls")),
    # OpenAPI docs
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]

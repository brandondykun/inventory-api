"""Root URL configuration."""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from apps.common.views import health_check

urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz/", health_check, name="health-check"),
    path("api/auth/", include("apps.authentication.urls")),
    path("api/users/", include("apps.users.urls")),
    path("api/", include("apps.organizations.urls")),
    # allauth's account routes (email confirmation, password reset). Mounted so
    # verification/reset links in emails resolve out of the box. A fork with its
    # own SPA/mobile frontend can instead override the adapter's
    # get_email_confirmation_url() to point links at the frontend.
    path("accounts/", include("allauth.urls")),
]

# Interactive API documentation — only mounted when explicitly enabled
# (on in dev/staging, off in production).
if settings.ENABLE_API_DOCS:
    from drf_spectacular.views import (
        SpectacularAPIView,
        SpectacularRedocView,
        SpectacularSwaggerView,
    )

    urlpatterns += [
        path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
        path(
            "api/schema/swagger-ui/",
            SpectacularSwaggerView.as_view(url_name="schema"),
            name="swagger-ui",
        ),
        path(
            "api/schema/redoc/",
            SpectacularRedocView.as_view(url_name="schema"),
            name="redoc",
        ),
    ]

# django-debug-toolbar (dev only).
if settings.DEBUG and "debug_toolbar" in settings.INSTALLED_APPS:
    urlpatterns += [path("__debug__/", include("debug_toolbar.urls"))]

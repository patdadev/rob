from __future__ import annotations

from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve
from django.conf import settings

from rob_admin import views as portal_views

urlpatterns = [
    path("portal/admin/login/", portal_views.admin_login_redirect, name="portal_admin_login_redirect"),
    path("portal/admin/", admin.site.urls),
    path("portal/", include("rob_admin.urls")),
    re_path(r"^portal/static/(?P<path>.*)$", serve, {"document_root": settings.STATIC_ROOT}),
]


from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework.routers import DefaultRouter

from core import views as core_views
from observations.api import ObservationViewSet, StationViewSet

router = DefaultRouter()
router.register("observations", ObservationViewSet, basename="api-observations")
router.register("stations", StationViewSet, basename="api-stations")


from django.http import HttpResponse
from pathlib import Path

# /favicon.ico отдаём готовыми PNG-байтами (32px) с годовым кэшем —
# без редиректов и генерации на лету
_FAVICON_PNG = (Path(__file__).resolve().parent.parent
                / "static" / "img" / "favicon-32.png").read_bytes()

urlpatterns = [
    path("favicon.ico", lambda r: HttpResponse(
        _FAVICON_PNG, content_type="image/png",
        headers={"Cache-Control": "public, max-age=31536000, immutable"})),
    path("admin/", admin.site.urls),          # административная панель (FR-009)
    path("", include("observations.urls")),   # карта, наблюдения, модерация
    path("accounts/", include("accounts.urls")),
    path("stations/", include("stations.urls")),
    path("reports/", include("reports.urls")),
    path("notifications/", core_views.notifications, name="notifications"),
    path("api/notifications/", core_views.api_notifications, name="api_notifications"),
    path("dashboard/", core_views.dashboard, name="dashboard"),
    path("api/dashboard-data/", core_views.api_dashboard, name="api_dashboard"),
    path("privacy/", core_views.privacy, name="privacy"),
    path("healthz", core_views.healthz, name="healthz"),
    path("sw.js", core_views.service_worker, name="service_worker"),
    # Вход через сторонние сервисы (VK ID) — allauth
    path("auth/", include("allauth.urls")),
    # Точка входа API (ТЗ 4.7.3): приём данных + документация OpenAPI
    path("api/v1/", include(router.urls)),
    path("api/v1/token/", obtain_auth_token, name="api_token"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="api_docs"),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

admin.site.site_header = "Дневник синоптика — администрирование"
admin.site.site_title = "Дневник синоптика"
admin.site.index_title = "Управление системой"
admin.site.enable_nav_sidebar = False   # боковая панель перекрывала контент и не закрывалась

from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path

from ai.views import my_performance
from institutions import views as institution_views


def health(request):
    return JsonResponse({"status": "ok"})


admin.site.site_header = "Cohortix platform admin"
admin.site.site_title = "Cohortix admin"
admin.site.index_title = "Institutions, people and tests"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health", health),
    path("api/auth/", include("accounts.urls")),
    path("api/ai/", include("ai.urls")),
    path("api/institution", institution_views.profile),
    path("api/institution/", include("institutions.urls")),
    path("api/institutions/by-slug/<slug:slug>", institution_views.branding),
    path("api/institutions/<str:institution_id>/logo", institution_views.logo),
    path("api/me/performance", my_performance),
    path("api/board/", include("board.urls")),
    path("api/reports/", include("reports.urls")),
    path("api/", include("assessments.urls")),
]

from django.urls import path

from . import views

urlpatterns = [
    path("logo", views.institution_logo),
    path("overview", views.overview),
    path("activity", views.activity),
    path("users", views.users),
    path("users/import", views.import_users),
    path("users/export", views.export_users),
    path("users/<str:user_id>", views.user_detail),
    path("users/<str:user_id>/reset-password", views.reset_password),
    path("structure", views.academic_structure),
    path("structure/<str:level>/<str:node_id>", views.group_detail),
]

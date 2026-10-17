from django.urls import path

from . import views

urlpatterns = [
    path("logo", views.institution_logo),
    path("overview", views.overview),
    path("activity", views.activity),
    path("users", views.users),
    path("users/import", views.import_users),
    path("users/<str:user_id>/reset-password", views.reset_password),
    path("cohorts", views.cohorts),
    path("cohorts/<str:cohort_id>", views.cohort_detail),
]

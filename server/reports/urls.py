from django.urls import path

from . import views

urlpatterns = [
    path("me", views.my_report),
    path("overview", views.overview),
    path("students/<str:student_id>", views.student_report),
]

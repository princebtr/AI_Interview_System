from django.urls import path

from . import views

urlpatterns = [
    path("login", views.login),
    path("logout", views.logout),
    path("logout-all", views.logout_all),
    path("me", views.me),
    path("updatedetails", views.update_details),
    path("updatepassword", views.update_password),
]

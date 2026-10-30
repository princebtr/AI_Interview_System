from django.urls import path

from . import views

urlpatterns = [
    path("posts", views.posts),
    path("unread", views.unread),
    path("posts/<str:post_id>", views.post_detail),
    path("posts/<str:post_id>/read", views.mark_read),
    path("posts/<str:post_id>/comments", views.comments),
    path("posts/<str:post_id>/comments/<str:comment_id>", views.comment_detail),
    path("posts/<str:post_id>/reactions/<str:kind>", views.reaction),
    path("posts/<str:post_id>/attachments", views.add_attachments),
    path("posts/<str:post_id>/attachments/<str:attachment_id>", views.attachment_detail),
]

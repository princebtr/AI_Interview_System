from django.urls import path

from . import views

urlpatterns = [
    path("generate-question", views.generate_question),
    path("evaluate-answer", views.evaluate_answer),
    path("generate-mcq-questions", views.generate_mcq_questions),
    path("evaluate-mcq-answers", views.evaluate_mcq_answers),
    path("proctoring-config", views.proctoring_config),
    path("analyse-frame", views.analyse_frame),
    path("detect-faces", views.detect_faces),
    path("detect-phone", views.detect_phone),
    path("session", views.start_session),
    path("practice/<str:quiz_id>", views.practice_status),
    path("practice/<str:quiz_id>/violations", views.practice_violation),
    path("practice/<str:quiz_id>/frame", views.practice_frame),
]

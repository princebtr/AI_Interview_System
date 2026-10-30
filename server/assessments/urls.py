from django.urls import path

from . import assessment_views as tests
from . import views

urlpatterns = [
    path("questions", views.questions),
    path("questions/import", views.import_questions),
    path("questions/<str:question_id>", views.question_detail),
    path("teaching/overview", views.overview),
    path("teaching/students", views.students),
    path("assessments", tests.assessments),
    path("proctoring/capabilities", tests.monitoring_capabilities),
    path("assessments/<str:assessment_id>", tests.assessment_detail),
    path("assessments/<str:assessment_id>/violations", tests.assessment_violations),
    path("assessments/<str:assessment_id>/violations/<str:event_id>", tests.review_violation),
    path("me/tests", tests.my_tests),
    path("me/tests/<str:assessment_id>", tests.my_test),
    path("me/tests/<str:assessment_id>/start", tests.start_test),
    path("me/tests/<str:assessment_id>/answers", tests.save_test_answers),
    path("me/tests/<str:assessment_id>/submit", tests.submit_test),
    path("me/tests/<str:assessment_id>/violations", tests.report_violation),
    path("me/tests/<str:assessment_id>/frame", tests.check_frame),
]

from django.urls import path
from . import views

app_name = "jobs"

urlpatterns = [
    path("", views.JobListCreateView.as_view(), name="job_list_create"),
    path("<int:pk>/", views.JobDetailView.as_view(), name="job_detail"),
    path("<int:pk>/accept/", views.accept_job, name="accept_job"),
    path("<int:pk>/start/", views.start_job, name="start_job"),
    path("<int:pk>/end/", views.end_job, name="end_job"),
    path("<int:pk>/cancel/", views.cancel_job, name="cancel_job"),
    path("open/", views.OpenJobsView.as_view(), name="open_jobs"),
]

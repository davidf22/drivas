from django.urls import path
from . import views

app_name = "messaging"

urlpatterns = [
    path("", views.chat_view, name="chat"),
    path("send/", views.send_message, name="send_message"),
    path("job-action/", views.job_action, name="job_action"),
]

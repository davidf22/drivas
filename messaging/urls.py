from django.urls import path
from . import views

app_name = "messaging"

urlpatterns = [
    path("", views.chat_view, name="chat"),
    path("send/", views.send_message, name="send_message"),
    path("poll/", views.poll_messages, name="poll_messages"),
    path("job-action/", views.job_action, name="job_action"),
    path("contract/<int:job_id>/", views.download_contract, name="download_contract"),
    path("upload-license/", views.upload_license, name="upload_license"),
    path("pay/<int:job_id>/", views.pay_salary, name="pay_salary"),
    path("pay/callback/", views.pay_callback, name="pay_callback"),
    path("pay/webhook/", views.pay_webhook, name="pay_webhook"),
]

from django.urls import path
from . import views

app_name = "messaging"

urlpatterns = [
    path("", views.chat_view, name="chat"),
    path("send/", views.send_message, name="send_message"),
]

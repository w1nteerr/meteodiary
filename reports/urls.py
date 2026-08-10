from django.urls import path
from . import views

urlpatterns = [
    path("new/", views.report_create, name="report_create"),
    path("my/", views.report_list, name="report_list"),
]

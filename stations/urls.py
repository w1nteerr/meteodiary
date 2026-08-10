from django.urls import path
from . import views

urlpatterns = [
    path("", views.station_list, name="station_list"),
    path("new/", views.station_create, name="station_create"),
    path("<int:pk>/page/", views.station_public, name="station_public"),
    path("<int:pk>/edit/", views.station_edit, name="station_edit"),
    path("<int:pk>/archive/", views.station_toggle_archive, name="station_archive"),
    path("<int:pk>/delete/", views.station_delete, name="station_delete"),
]

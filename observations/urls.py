from django.urls import path
from . import views

urlpatterns = [
    path("", views.map_view, name="map"),
    path("api/map-data/", views.api_map_data, name="api_map_data"),
    path("observations/new/", views.observation_create, name="observation_create"),
    path("observations/anonymous/", views.observation_create_anon, name="observation_create_anon"),
    path("api/weather-prefill/", views.api_weather_prefill, name="api_weather_prefill"),
    path("observations/my/", views.my_observations, name="my_observations"),
    path("observations/<int:pk>/rework/", views.observation_rework, name="observation_rework"),
    path("observations/<int:pk>/delete/", views.observation_delete, name="observation_delete"),
    path("moderation/", views.moderation_queue, name="moderation_queue"),
    path("moderation/<int:pk>/", views.moderation_detail, name="moderation_detail"),
]

from django.contrib import admin
from .models import Station


@admin.register(Station)
class StationAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "latitude", "longitude", "is_public", "is_active")
    list_filter = ("is_public", "is_active")

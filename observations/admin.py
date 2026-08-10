from django.contrib import admin
from .models import Allergen, Observation, Photo, ModerationLog, PrecipitationType, Phenomenon


class PhotoInline(admin.TabularInline):
    model = Photo
    extra = 0


@admin.register(Observation)
class ObservationAdmin(admin.ModelAdmin):
    list_display = ("id", "obs_type", "station", "author", "observed_at", "status",
                    "is_anomaly", "resubmit_count", "moderator")
    list_filter = ("status", "is_anomaly", "obs_type")
    date_hierarchy = "observed_at"
    inlines = [PhotoInline]


@admin.register(ModerationLog)
class ModerationLogAdmin(admin.ModelAdmin):
    list_display = ("observation", "moderator", "action", "old_status",
                    "new_status", "ip", "created_at")
    list_filter = ("action",)


@admin.register(PrecipitationType)
class PrecipAdmin(admin.ModelAdmin):
    """Порядок ведения справочников — ТЗ п. 3.4: значения не удаляются,
    только помечаются неактивными."""
    list_display = ("code", "name", "is_active")

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Phenomenon)
class PhenomenonAdmin(PrecipAdmin):
    pass


@admin.register(Allergen)
class AllergenAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active")
    list_editable = ("is_active",)

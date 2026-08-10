"""FR-004: валидация координат, границы Республики Коми, контроль дублей."""
from django import forms
from django.conf import settings
from core.services import haversine_km
from .models import Station


class StationForm(forms.ModelForm):
    class Meta:
        model = Station
        fields = ["name", "latitude", "longitude", "height", "location_type",
                  "description", "equipment", "is_public"]

    def __init__(self, *args, owner=None, **kwargs):
        self.owner = owner
        super().__init__(*args, **kwargs)

    def clean_latitude(self):
        lat = self.cleaned_data["latitude"]
        if not (-90 <= lat <= 90):
            raise forms.ValidationError("Широта должна быть в диапазоне от −90 до +90.")
        return lat

    def clean_longitude(self):
        lon = self.cleaned_data["longitude"]
        if not (-180 <= lon <= 180):
            raise forms.ValidationError("Долгота должна быть в диапазоне от −180 до +180.")
        return lon

    def clean(self):
        data = super().clean()
        lat, lon = data.get("latitude"), data.get("longitude")
        if lat is None or lon is None:
            return data
        bb = settings.RUSSIA_BBOX
        # Упрощённая проверка принадлежности стране (bbox) — отсеивает опечатки.
        if not (bb["lat_min"] <= float(lat) <= bb["lat_max"]
                and bb["lon_min"] <= float(lon) <= bb["lon_max"]):
            raise forms.ValidationError(
                "Точка находится за пределами России — проверьте координаты.")
        owner = self.owner or (self.instance.owner_id and self.instance.owner)
        qs = Station.objects.filter(owner=owner)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        for st in qs:
            if haversine_km(lat, lon, st.latitude, st.longitude) * 1000 < settings.STATION_MIN_DISTANCE_M:
                raise forms.ValidationError(
                    f"У вас уже есть точка «{st.name}» ближе {settings.STATION_MIN_DISTANCE_M} м. "
                    "Используйте существующую точку.")
        return data

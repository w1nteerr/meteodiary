"""Сущность «Точка наблюдения» (ТЗ 4.7.1)."""
from django.conf import settings
from django.db import models


class LocationType(models.TextChoices):
    INLAND = "inland", "Материковая"
    COAST = "coast", "Побережье"
    ISLAND = "island", "Остров"


class Station(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                              related_name="stations", verbose_name="владелец")
    name = models.CharField("наименование", max_length=120)
    latitude = models.DecimalField("широта", max_digits=9, decimal_places=6)
    longitude = models.DecimalField("долгота", max_digits=9, decimal_places=6)
    height = models.DecimalField("высота над уровнем моря, м", max_digits=7,
                                 decimal_places=1, null=True, blank=True)
    location_type = models.CharField("тип местности", max_length=10,
        choices=LocationType.choices, default=LocationType.INLAND,
        help_text="для побережья и островов доступна температура воды; "
                  "для островов скорость ветра дублируется в узлах")
    description = models.TextField("описание", blank=True)
    equipment = models.TextField("оборудование", blank=True)
    is_public = models.BooleanField("публичная", default=True)   # FR-004: по умолчанию публична
    is_active = models.BooleanField("активна", default=True)      # архивация (FR-014)
    created_at = models.DateTimeField("дата создания", auto_now_add=True)
    updated_at = models.DateTimeField("дата изменения", auto_now=True)

    class Meta:
        verbose_name = "точка наблюдения"
        verbose_name_plural = "точки наблюдения"
        # В PostGIS дополнительно создаётся GiST-индекс по геометрии (ТЗ 4.7.1)
        indexes = [models.Index(fields=["is_public", "is_active"])]

    def __str__(self):
        return self.name

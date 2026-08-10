"""Сущности «Наблюдение», «Фото», справочники, «Журнал модерации» (ТЗ 4.7.1)."""
import uuid
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models


class PrecipitationType(models.Model):
    code = models.SlugField("код", max_length=32, unique=True)
    name = models.CharField("наименование", max_length=64)
    is_active = models.BooleanField("активен", default=True)

    class Meta:
        verbose_name = "тип осадков"
        verbose_name_plural = "справочник: типы осадков"

    def __str__(self):
        return self.name


class Phenomenon(models.Model):
    code = models.SlugField("код", max_length=32, unique=True)
    name = models.CharField("наименование", max_length=64)
    is_active = models.BooleanField("активен", default=True)

    class Meta:
        verbose_name = "погодное явление"
        verbose_name_plural = "справочник: погодные явления"

    def __str__(self):
        return self.name


# Русские подписи румбов: в БД хранится код (N, SW…), пользователю
# показывается русское обозначение (С, ЮЗ…)
WIND_RU = {"N": "С", "NNE": "ССВ", "NE": "СВ", "ENE": "ВСВ",
           "E": "В", "ESE": "ВЮВ", "SE": "ЮВ", "SSE": "ЮЮВ",
           "S": "Ю", "SSW": "ЮЮЗ", "SW": "ЮЗ", "WSW": "ЗЮЗ",
           "W": "З", "WNW": "ЗСЗ", "NW": "СЗ", "NNW": "ССЗ"}
WIND_DIRECTIONS = ["N","NNE","NE","ENE","E","ESE","SE","SSE",
                   "S","SSW","SW","WSW","W","WNW","NW","NNW"]


class Allergen(models.Model):
    """Справочник аллергенов для аллергонаблюдений (пыльца, споры, пух)."""
    code = models.SlugField("код", max_length=32, unique=True)
    name = models.CharField("наименование", max_length=64)
    is_active = models.BooleanField("активен", default=True)

    class Meta:
        verbose_name = "аллерген"
        verbose_name_plural = "справочник: аллергены"

    def __str__(self):
        return self.name


class ObsType(models.TextChoices):
    """Типы наблюдений: наблюдатель заполняет только нужные поля,
    а не всю форму целиком."""
    FULL = "full", "Полное наблюдение"
    EXPRESS = "express", "Экспресс-замер"
    ALLERGY = "allergy", "Аллергонаблюдение"


class PollenLevel(models.TextChoices):
    LOW = "low", "Низкий"
    MEDIUM = "medium", "Средний"
    HIGH = "high", "Высокий"
    VERY_HIGH = "very_high", "Очень высокий"


class Status(models.TextChoices):
    """Машина состояний (ТЗ 4.7.1): draft→pending→approved/rework/rejected."""
    DRAFT = "draft", "Черновик"
    PENDING = "pending", "На проверке"
    APPROVED = "approved", "Подтверждено"
    REWORK = "rework", "Доработка"
    REJECTED = "rejected", "Отклонено"


class Observation(models.Model):
    client_uuid = models.UUIDField("клиентский идентификатор", default=uuid.uuid4,
                                   unique=True, editable=False)  # идемпотентность FR-005
    station = models.ForeignKey("stations.Station", on_delete=models.PROTECT,
                                related_name="observations", verbose_name="точка")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                               related_name="observations", verbose_name="автор")
    observed_at = models.DateTimeField("дата и время замера")
    obs_type = models.CharField("тип наблюдения", max_length=10,
        choices=ObsType.choices, default=ObsType.FULL)
    temperature = models.DecimalField("температура, °C", max_digits=4, decimal_places=1,
        null=True, blank=True,
        validators=[MinValueValidator(-60), MaxValueValidator(60)])
    pressure = models.DecimalField("давление, гПа", max_digits=5, decimal_places=1,
        null=True, blank=True,
        validators=[MinValueValidator(600), MaxValueValidator(1100)])
    wind_speed = models.DecimalField("скорость ветра, м/с", max_digits=4, decimal_places=1,
        null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)])
    wind_direction = models.CharField("направление ветра (румб)", max_length=3, blank=True,
        choices=[(d, WIND_RU[d]) for d in WIND_DIRECTIONS])
    precipitation_amount = models.DecimalField("кол-во осадков, мм", max_digits=4,
        decimal_places=1, default=0, validators=[MinValueValidator(0), MaxValueValidator(500)])
    precipitation_type = models.ForeignKey(PrecipitationType, on_delete=models.PROTECT,
                                           null=True, blank=True,
                                           verbose_name="тип осадков")
    cloudiness = models.PositiveSmallIntegerField("облачность, %",
        null=True, blank=True, validators=[MaxValueValidator(100)])
    water_temperature = models.DecimalField("температура воды, °C", max_digits=4,
        decimal_places=1, null=True, blank=True,
        validators=[MinValueValidator(-2), MaxValueValidator(35)],
        help_text="заполняется для точек на побережье и островах")
    phenomena = models.ManyToManyField(Phenomenon, blank=True, verbose_name="явления")
    # --- аллергонаблюдение ---
    pollen_level = models.CharField("уровень пыльцы", max_length=10, blank=True,
        choices=PollenLevel.choices)
    allergen = models.ForeignKey(Allergen, on_delete=models.PROTECT,
        null=True, blank=True, verbose_name="аллерген")

    status = models.CharField("статус", max_length=10, choices=Status.choices,
                              default=Status.PENDING)
    is_anomaly = models.BooleanField("аномалия", default=False)
    resubmit_count = models.PositiveSmallIntegerField("повторных отправок", default=0)
    moderator = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="moderated", verbose_name="модератор")
    moderated_at = models.DateTimeField("дата модерации", null=True, blank=True)
    version = models.PositiveIntegerField("версия", default=1)
    extra = models.JSONField("доп. атрибуты", default=dict, blank=True)
    is_archived = models.BooleanField("архив", default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "наблюдение"
        verbose_name_plural = "наблюдения"
        ordering = ["-observed_at"]
        indexes = [
            models.Index(fields=["status", "observed_at"]),   # очередь модерации/карта (ТЗ 4.7.1)
            models.Index(fields=["station"]),
            models.Index(fields=["author"]),
        ]

    def __str__(self):
        return f"{self.station} {self.observed_at:%d.%m.%Y %H:%M}"


class Photo(models.Model):
    observation = models.ForeignKey(Observation, on_delete=models.CASCADE,
                                    related_name="photos", verbose_name="наблюдение")
    image = models.ImageField("изображение", upload_to="photos/%Y/%m/")
    size = models.PositiveIntegerField("размер, байт", default=0)
    uploaded_at = models.DateTimeField("дата загрузки", auto_now_add=True)

    class Meta:
        verbose_name = "фото"
        verbose_name_plural = "фото"


class ModerationLog(models.Model):
    observation = models.ForeignKey(Observation, on_delete=models.CASCADE,
                                    related_name="moderation_log", verbose_name="наблюдение")
    moderator = models.ForeignKey(settings.AUTH_USER_MODEL, null=True,
        on_delete=models.SET_NULL, verbose_name="модератор")
    action = models.CharField("действие", max_length=32)
    old_status = models.CharField("старый статус", max_length=10, choices=Status.choices)
    new_status = models.CharField("новый статус", max_length=10, choices=Status.choices)
    comment = models.TextField("комментарий", blank=True)
    ip = models.GenericIPAddressField("IP-адрес", null=True, blank=True)
    created_at = models.DateTimeField("дата и время", auto_now_add=True)

    class Meta:
        verbose_name = "запись журнала модерации"
        verbose_name_plural = "журнал модерации"
        ordering = ["-created_at"]

"""Отчёты (FR-008): фоновая генерация, хранение 7 суток, раздел «Мои отчёты»."""
from django.conf import settings
from django.db import models


class Report(models.Model):
    class Fmt(models.TextChoices):
        CSV = "csv", "CSV"
        PDF = "pdf", "PDF"

    class State(models.TextChoices):
        PENDING = "pending", "Формируется"
        READY = "ready", "Готов"
        EMPTY = "empty", "Нет данных"
        ERROR = "error", "Ошибка"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name="reports", verbose_name="пользователь")
    station = models.ForeignKey("stations.Station", null=True, blank=True,
                                on_delete=models.SET_NULL,
                                verbose_name="точка (пусто — весь регион)")
    date_from = models.DateField("период с")
    date_to = models.DateField("период по")
    fmt = models.CharField("формат", max_length=4, choices=Fmt.choices, default=Fmt.CSV)
    state = models.CharField("состояние", max_length=8, choices=State.choices,
                             default=State.PENDING)
    file = models.FileField("файл", upload_to="reports/", blank=True)
    created_at = models.DateTimeField("создан", auto_now_add=True)

    class Meta:
        verbose_name = "отчёт"
        verbose_name_plural = "отчёты"
        ordering = ["-created_at"]

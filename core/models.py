"""Сущности «Уведомление» и «Журнал действий» (ТЗ 4.7.1)."""
from django.conf import settings
from django.db import models


class Notification(models.Model):
    class Type(models.TextChoices):
        STATUS = "status", "Смена статуса наблюдения"
        REPORT = "report", "Готовность отчёта"
        MODERATION = "moderation", "Назначение модерации"
        OTHER = "other", "Прочее"

    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                  related_name="notifications", verbose_name="получатель")
    ntype = models.CharField("тип", max_length=16, choices=Type.choices, default=Type.OTHER)
    text = models.CharField("текст", max_length=500)
    link = models.CharField("ссылка", max_length=255, blank=True)
    is_read = models.BooleanField("прочитано", default=False)
    created_at = models.DateTimeField("создано", auto_now_add=True)

    class Meta:
        verbose_name = "уведомление"
        verbose_name_plural = "уведомления"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["recipient", "is_read"])]


class AuditLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                             on_delete=models.SET_NULL, verbose_name="пользователь")
    action = models.CharField("действие", max_length=64)
    obj = models.CharField("объект", max_length=255, blank=True)
    old_value = models.TextField("старое значение", blank=True)
    new_value = models.TextField("новое значение", blank=True)
    reason = models.CharField("причина", max_length=255, blank=True)
    ip = models.GenericIPAddressField("IP-адрес", null=True, blank=True)
    user_agent = models.CharField("User-Agent", max_length=255, blank=True)
    created_at = models.DateTimeField("дата и время", auto_now_add=True)

    class Meta:
        verbose_name = "запись журнала действий"
        verbose_name_plural = "журнал действий"
        ordering = ["-created_at"]

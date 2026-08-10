"""Бизнес-логика: проверка аномалий (FR-005), смена статусов (FR-006/FR-010)."""
from datetime import timedelta
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.utils.timezone import localtime

from core.services import haversine_km, notify, audit
from core.models import Notification
from .models import Observation, Status, ModerationLog


def check_anomaly(obs):
    """Критерии аномалии по ТЗ FR-005 (а–д). Не блокирует отправку — только флаг."""
    cfg = settings.ANOMALY
    reasons = []
    # После появления типов наблюдений часть метеополей может быть пустой
    # (экспресс- и аллергонаблюдения) — проверяем только заполненные значения
    if obs.wind_speed is not None and float(obs.wind_speed) > cfg["wind_max"]:
        reasons.append("скорость ветра > 40 м/с")
    if obs.precipitation_amount is not None and \
            float(obs.precipitation_amount) > cfg["precip_max"]:
        reasons.append("осадки > 100 мм")
    if obs.precipitation_type_id and obs.precipitation_type.code == "snow" \
            and obs.temperature is not None and float(obs.temperature) > 15:
        reasons.append("снег при температуре выше +15 °C")

    # (а), (б): сравнение с ближайшим подтверждённым наблюдением (50 км, ±3 ч).
    # В продакшене — один запрос PostGIS ST_DWithin; здесь хаверсин по кандидатам.
    window = timedelta(hours=cfg["neighbor_hours"])
    candidates = (Observation.objects
                  .filter(status=Status.APPROVED,
                          observed_at__range=(obs.observed_at - window, obs.observed_at + window))
                  .exclude(pk=obs.pk)
                  .select_related("station")[:500])
    nearest = None
    nearest_d = None
    for c in candidates:
        d = haversine_km(obs.station.latitude, obs.station.longitude,
                         c.station.latitude, c.station.longitude)
        if d <= cfg["neighbor_radius_km"] and (nearest_d is None or d < nearest_d):
            nearest, nearest_d = c, d
    if nearest:
        if obs.temperature is not None and nearest.temperature is not None and \
                abs(float(obs.temperature) - float(nearest.temperature)) > cfg["temp_delta"]:
            reasons.append(f"температура отличается от соседней точки более чем на {cfg['temp_delta']} °C")
        if obs.pressure is not None and nearest.pressure is not None and \
                abs(float(obs.pressure) - float(nearest.pressure)) > cfg["pressure_delta"]:
            reasons.append(f"давление отличается от соседней точки более чем на {cfg['pressure_delta']} гПа")

    # (е) временная согласованность: резкий скачок к предыдущему замеру той же
    # точки (стандартный шаг контроля качества краудсорсинговых метеосетей)
    prev = (Observation.objects
            .filter(station=obs.station,
                    status__in=[Status.APPROVED, Status.PENDING],
                    observed_at__lt=obs.observed_at,
                    observed_at__gte=obs.observed_at - timedelta(hours=cfg["jump_hours"]))
            .exclude(pk=obs.pk).order_by("-observed_at").first())
    if prev and obs.temperature is not None and prev.temperature is not None and \
            abs(float(obs.temperature) - float(prev.temperature)) > cfg["temp_jump"]:
        reasons.append(
            f"скачок температуры более {cfg['temp_jump']} °C относительно предыдущего замера точки")

    obs.is_anomaly = bool(reasons)
    obs.extra["anomaly_reasons"] = reasons
    return obs


def moderate(request, obs, decision, comment):
    """FR-006: подтвердить / отклонить / на доработку. Модератор не редактирует данные."""
    mapping = {"approve": Status.APPROVED, "reject": Status.REJECTED, "rework": Status.REWORK}
    new_status = mapping[decision]
    old_status = obs.status
    obs.status = new_status
    obs.moderator = request.user
    obs.moderated_at = timezone.now()
    obs.save(update_fields=["status", "moderator", "moderated_at", "updated_at"])
    ModerationLog.objects.create(
        observation=obs, moderator=request.user, action=decision,
        old_status=old_status, new_status=new_status, comment=comment,
        ip=request.META.get("REMOTE_ADDR"))
    audit(request, f"moderate_{decision}", obj=f"observation:{obs.pk}",
          old=old_status, new=new_status)
    notify(obs.author,
           f"Наблюдение от {localtime(obs.observed_at):%d.%m.%Y %H:%M} ({obs.station}): "
           f"новый статус — «{obs.get_status_display()}». {('Комментарий: ' + comment) if comment else ''}",
           ntype=Notification.Type.STATUS, link=reverse("my_observations"))


def resubmit(request, obs):
    """FR-010: доработка → повторная отправка (лимит 3), уведомление модераторам."""
    obs.status = Status.PENDING
    obs.resubmit_count += 1
    obs.version += 1
    obs = check_anomaly(obs)
    obs.save()
    ModerationLog.objects.create(
        observation=obs, moderator=None, action="resubmit",
        old_status=Status.REWORK, new_status=Status.PENDING,
        comment=f"Повторная отправка №{obs.resubmit_count}",
        ip=request.META.get("REMOTE_ADDR"))
    audit(request, "observation_resubmit", obj=f"observation:{obs.pk}")
    from accounts.models import User, Roles
    for m in User.objects.filter(role__in=[Roles.MODERATOR, Roles.ADMIN], is_active=True):
        notify(m, f"Наблюдение №{obs.pk} повторно отправлено на модерацию "
                  f"(отправка №{obs.resubmit_count}).",
               ntype=Notification.Type.MODERATION, link=reverse("moderation_queue"),
               email=False)

"""Сервисы: аудит (ТЗ 4.4), уведомления (FR-006/FR-008), гео-утилиты."""
import math
from django.core.mail import send_mail
from .models import AuditLog, Notification


def audit(request, action, obj="", old="", new="", reason=""):
    AuditLog.objects.create(
        user=request.user if getattr(request, "user", None) and request.user.is_authenticated else None,
        action=action, obj=obj, old_value=str(old), new_value=str(new), reason=reason,
        ip=request.META.get("REMOTE_ADDR"),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
    )


def notify(user, text, ntype=Notification.Type.OTHER, link="", email=True):
    """Внутрисистемное уведомление + дублирование по e-mail (ТЗ FR-006)."""
    Notification.objects.create(recipient=user, ntype=ntype, text=text, link=link)
    if email and user.email:
        try:
            send_mail("Дневник синоптика: уведомление", text, None, [user.email],
                      fail_silently=True)
        except Exception:
            pass


def haversine_km(lat1, lon1, lat2, lon2):
    """Расстояние между точками, км. В продакшене заменяется запросом PostGIS
    (ST_DWithin); для учебного запуска на SQLite считаем в Python."""
    r = 6371.0
    p1, p2 = math.radians(float(lat1)), math.radians(float(lat2))
    dp = p2 - p1
    dl = math.radians(float(lon2) - float(lon1))
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def build_weather_warnings(limit=9):
    """Простые погодные предупреждения по точкам за последние 24 часа.
    Формулировки нарочно короткие и человеческие («Вероятен дождь»)."""
    from datetime import timedelta
    from django.utils import timezone
    from observations.models import Observation, Status

    day_ago = timezone.now() - timedelta(hours=24)
    recent = (Observation.objects.filter(observed_at__gte=day_ago)
              .exclude(status=Status.REJECTED).select_related("station"))
    by_station = {}
    for o in recent:
        by_station.setdefault(o.station, []).append(o)

    warnings = []
    for station, obs in by_station.items():
        # часть полей может быть пустой (экспресс/аллерго) — считаем по заполненным
        winds = [float(o.wind_speed) for o in obs if o.wind_speed is not None]
        wind_max = max(winds) if winds else 0
        precip_sum = sum(float(o.precipitation_amount or 0) for o in obs)
        rain_share = sum(1 for o in obs if float(o.precipitation_amount or 0) > 0) / len(obs)
        temps_st = [float(o.temperature) for o in obs if o.temperature is not None]
        t_avg = sum(temps_st) / len(temps_st) if temps_st else None
        if wind_max >= 20:
            warnings.append({"level": "danger", "rank": 0, "station": station,
                             "text": f"Очень сильный ветер — порывы до {wind_max:.0f} м/с"})
        elif wind_max >= 12:
            warnings.append({"level": "warn", "rank": 1, "station": station,
                             "text": f"Сильный ветер — до {wind_max:.0f} м/с"})
        if precip_sum >= 15:
            warnings.append({"level": "warn", "rank": 1, "station": station,
                             "text": f"Сильные осадки — {precip_sum:.0f} мм за сутки"})
        elif rain_share >= 0.5:
            word = "снег" if (t_avg is not None and t_avg <= 0) else "дождь"
            warnings.append({"level": "info", "rank": 2, "station": station,
                             "text": f"Вероятен {word}"})
    # Аллергопредупреждения: высокий и очень высокий уровень пыльцы за сутки.
    # Формулировки в том же духе, что и погодные («Вероятен дождь»).
    for station, obs in by_station.items():
        pollen = [o for o in obs
                  if o.obs_type == "allergy" and o.pollen_level in ("high", "very_high")]
        if not pollen:
            continue
        worst = max(pollen, key=lambda o: 1 if o.pollen_level == "high" else 2)
        names = sorted({o.allergen.name for o in pollen if o.allergen_id})
        tail = f" — {', '.join(names[:2])}" if names else ""
        if worst.pollen_level == "very_high":
            warnings.append({"level": "danger", "rank": 0, "station": station,
                             "kind": "allergy",
                             "text": f"Очень высокий уровень пыльцы{tail}"})
        else:
            warnings.append({"level": "warn", "rank": 1, "station": station,
                             "kind": "allergy",
                             "text": f"Высокий уровень пыльцы{tail}"})

    warnings.sort(key=lambda w: w["rank"])
    return warnings[:limit]

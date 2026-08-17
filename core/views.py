from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.utils.timezone import localtime
from django.shortcuts import render


@login_required
def api_notifications(request):
    """JSON для колокольчика: последние уведомления и число непрочитанных.
    Используется выпадающей панелью и всплывающими тостами."""
    if not request.user.is_authenticated:
        return JsonResponse({"unread": 0, "items": []})
    if request.method == "POST":                      # отметить всё прочитанным
        request.user.notifications.filter(is_read=False).update(is_read=True)
        return JsonResponse({"ok": True})
    items = [{"id": n.pk, "text": n.text, "link": n.link,
              "type": n.get_ntype_display(), "is_read": n.is_read,
              "when": localtime(n.created_at).strftime("%d.%m %H:%M")}
             for n in request.user.notifications.all()[:10]]
    unread = request.user.notifications.filter(is_read=False).count()
    return JsonResponse({"unread": unread, "items": items})


@login_required
def notifications(request):
    qs = request.user.notifications.all()
    page = Paginator(qs, 20).get_page(request.GET.get("page"))
    request.user.notifications.filter(is_read=False).update(is_read=True)
    return render(request, "core/notifications.html", {"page": page})


def healthz(request):
    """Мониторинг доступности (ТЗ 4.3: опрос раз в 60 с для расчёта MTBF).
    Проверяет ответ приложения и доступность БД."""
    from django.db import connection
    from django.http import JsonResponse
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
        return JsonResponse({"status": "ok"})
    except Exception:
        return JsonResponse({"status": "error"}, status=503)


def service_worker(request):
    """Отдача sw.js с корня сайта: scope сервис-воркера должен покрывать «/»."""
    from django.conf import settings
    from django.http import HttpResponse
    path = settings.BASE_DIR / "static" / "js" / "sw.js"
    return HttpResponse(path.read_text(encoding="utf-8"),
                        content_type="application/javascript")


@login_required
def dashboard(request):
    """Личный дашборд (FR-007/FR-013): сводные показатели и графики.
    Состав блоков зависит от роли: наблюдатель видит свою статистику,
    модератор — очередь, администратор — пользователей."""
    from datetime import timedelta
    from django.db.models import Avg, Min, Max
    from django.utils import timezone
    from observations.models import Observation, Status
    from stations.models import Station

    now = timezone.now()
    month_ago = now - timedelta(days=30)
    approved = Observation.objects.filter(status=Status.APPROVED, is_archived=False)

    ctx = {
        "total_approved": approved.count(),
        "month_approved": approved.filter(observed_at__gte=month_ago).count(),
        "stations_active": Station.objects.filter(is_active=True).count(),
        "my_observations": request.user.observations.filter(is_archived=False).count(),
        "my_pending": request.user.observations.filter(status=Status.PENDING).count(),
        "my_rework": request.user.observations.filter(status=Status.REWORK).count(),
        "my_stations": request.user.stations.filter(is_active=True).count(),
        "agg": approved.filter(observed_at__gte=month_ago).aggregate(
            t_min=Min("temperature"), t_max=Max("temperature"),
            t_avg=Avg("temperature"), p_avg=Avg("pressure")),
    }
    # --- Достижения наблюдателя (геймификация): считаются по фактическим
    # данным пользователя; заработанные подсвечиваются, остальные — цели
    my = Observation.objects.filter(author=request.user)
    my_appr = my.filter(status=Status.APPROVED)
    n_appr = my_appr.count()
    days = sorted({o.date() for o in my.values_list("observed_at", flat=True)})
    best_streak, cur = (1, 1) if days else (0, 0)
    for a, b in zip(days, days[1:]):
        cur = cur + 1 if (b - a).days == 1 else 1
        best_streak = max(best_streak, cur)
    ctx["achievements"] = [
        {"icon": "🌱", "title": "Первые шаги", "earned": n_appr >= 1,
         "desc": "первое подтверждённое наблюдение"},
        {"icon": "📊", "title": "Постоянный наблюдатель", "earned": n_appr >= 10,
         "desc": f"10 подтверждённых наблюдений ({min(n_appr, 10)}/10)"},
        {"icon": "🏆", "title": "Ветеран сети", "earned": n_appr >= 50,
         "desc": f"50 подтверждённых наблюдений ({min(n_appr, 50)}/50)"},
        {"icon": "🔥", "title": "Серия", "earned": best_streak >= 7,
         "desc": f"наблюдения 7 дней подряд (рекорд: {best_streak})"},
        {"icon": "📷", "title": "Фотодокументалист", "earned":
            my.filter(photos__isnull=False).exists(),
         "desc": "наблюдение с фотографией"},
        {"icon": "🌪", "title": "Штормовой репортёр", "earned":
            my_appr.filter(wind_speed__gte=15).exists(),
         "desc": "замер при ветре от 15 м/с"},
        {"icon": "🧊", "title": "Полярник", "earned":
            my_appr.filter(temperature__lte=-20).exists(),
         "desc": "замер при морозе от −20 °C"},
        {"icon": "🗺", "title": "Картограф", "earned":
            request.user.stations.filter(is_active=True).count() >= 3,
         "desc": "три активные точки наблюдения"},
    ]

    if request.user.is_moderator:
        ctx["queue_count"] = Observation.objects.filter(status=Status.PENDING).count()
        ctx["queue_anomaly"] = Observation.objects.filter(
            status=Status.PENDING, is_anomaly=True).count()
    if request.user.is_admin_role:
        from django.contrib.auth import get_user_model
        U = get_user_model()
        ctx["users_total"] = U.objects.filter(is_deleted=False).count()
        ctx["users_blocked"] = U.objects.filter(is_blocked=True).count()
    return render(request, "core/dashboard.html", ctx)


@login_required
def api_dashboard(request):
    """Данные графиков дашборда за последние 30 дней."""
    from datetime import timedelta
    from django.db.models import Count
    from django.http import JsonResponse
    from django.utils import timezone
    from observations.models import Observation, Status

    now = timezone.now()
    month_ago = now - timedelta(days=30)
    qs = (Observation.objects
          .filter(is_archived=False, observed_at__gte=month_ago)
          .select_related("precipitation_type"))

    # ход температуры/давления — только подтверждённые, по времени
    # у экспресс- и аллергонаблюдений часть полей пустая — в ряд берём только
    # записи с температурой, давление отдаём как null (график его пропустит)
    series = [{"t": o.observed_at.isoformat(),
               "temp": float(o.temperature),
               "pressure": float(o.pressure) if o.pressure is not None else None}
              for o in qs.filter(status=Status.APPROVED, temperature__isnull=False)
                         .order_by("observed_at")[:500]]

    # осадки и количество наблюдений по дням
    daily = {}
    for o in qs.filter(status=Status.APPROVED):
        d = timezone.localtime(o.observed_at).date().isoformat()
        rec = daily.setdefault(d, {"precip": 0.0, "count": 0})
        rec["precip"] = round(rec["precip"] + float(o.precipitation_amount or 0), 1)
        rec["count"] += 1
    days = sorted(daily)

    # частота погодных явлений за 30 дней (для горизонтальной диаграммы)
    phen_rows = (qs.filter(status=Status.APPROVED)
                 .exclude(phenomena__isnull=True)
                 .values("phenomena__name").annotate(n=Count("id")).order_by("-n"))
    phenomena = {r["phenomena__name"]: r["n"] for r in phen_rows}

    # роза ветров: повторяемость направлений (16 румбов) и средняя скорость
    # по подтверждённым наблюдениям за 30 дней; штиль (пустой румб) не входит
    RUMBS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
             "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    rose = {r: {"n": 0, "speed": 0.0} for r in RUMBS}
    for o in qs.filter(status=Status.APPROVED).exclude(wind_direction=""):
        d = o.wind_direction
        if d in rose:
            rose[d]["n"] += 1
            rose[d]["speed"] += float(o.wind_speed or 0)
    wind_rose = {
        "labels": RUMBS,
        "counts": [rose[r]["n"] for r in RUMBS],
        "avg_speed": [round(rose[r]["speed"] / rose[r]["n"], 1) if rose[r]["n"] else 0
                      for r in RUMBS],
    }

    # распределение статусов (мои — для наблюдателя, все — для модератора)
    base = (Observation.objects.filter(is_archived=False)
            if request.user.is_moderator
            else request.user.observations.filter(is_archived=False))
    statuses = {row["status"]: row["n"]
                for row in base.values("status").annotate(n=Count("id"))}

    # --- аллергосводка за 30 дней: уровни пыльцы и топ аллергенов ---
    allergy_qs = qs.filter(status=Status.APPROVED, obs_type="allergy")
    pollen_counts = {row["pollen_level"]: row["n"] for row in allergy_qs
                     .exclude(pollen_level="").values("pollen_level")
                     .annotate(n=Count("id"))}
    top_allergens = list(allergy_qs.filter(allergen__isnull=False)
                         .values("allergen__name").annotate(n=Count("id"))
                         .order_by("-n")[:5])
    # уровень аллергии по каждому аллергену за 30 дней: берём МАКСИМАЛЬНЫЙ
    # зафиксированный уровень пыльцы для аллергена (1..4) — это отвечает на
    # вопрос «насколько сейчас опасен каждый аллерген», а не «сколько замеров»
    LEVEL_RANK = {"low": 1, "medium": 2, "high": 3, "very_high": 4}
    per_allergen = {}
    for o in allergy_qs.filter(allergen__isnull=False).exclude(pollen_level=""):
        name = o.allergen.name
        rank = LEVEL_RANK.get(o.pollen_level, 0)
        cur = per_allergen.get(name)
        # храним максимальный уровень и общее число наблюдений по аллергену
        if cur is None or rank > cur["level"]:
            per_allergen[name] = {"level": rank, "count": cur["count"] + 1 if cur else 1}
        else:
            cur["count"] += 1
    # сортируем по уровню опасности, затем по числу наблюдений
    allergen_levels = sorted(
        ({"name": n, "level": v["level"], "count": v["count"]}
         for n, v in per_allergen.items()),
        key=lambda a: (-a["level"], -a["count"]))

    # Общая сводка за 30 дней вместо «последнего наблюдения»: показываем
    # ПИКОВЫЙ уровень по всем точкам, число охваченных точек и аллергенов —
    # это честно отражает выборку с разных мест, а не одну случайную точку.
    LEVEL_LABELS = {1: "Низкий", 2: "Средний", 3: "Высокий", 4: "Очень высокий"}
    peak_level = max((a["level"] for a in allergen_levels), default=0)
    peak_code = {1: "low", 2: "medium", 3: "high", 4: "very_high"}.get(peak_level, "")
    # аллергены, у которых зафиксирован этот пиковый уровень
    peak_allergens = [a["name"] for a in allergen_levels if a["level"] == peak_level]
    stations_count = allergy_qs.values("station").distinct().count()

    allergy = {
        "total": allergy_qs.count(),
        "pollen": pollen_counts,
        "pollen_labels": {"low": "Низкий", "medium": "Средний",
                          "high": "Высокий", "very_high": "Очень высокий"},
        "top": [{"name": a["allergen__name"], "n": a["n"]} for a in top_allergens],
        "by_allergen": allergen_levels,
        "summary": {
            "peak_level": peak_level,
            "peak_code": peak_code,
            "peak_label": LEVEL_LABELS.get(peak_level, "—"),
            "peak_allergens": peak_allergens,
            "stations": stations_count,
            "allergens": len(allergen_levels),
        },
    }

    return JsonResponse({
        "series": series,
        "allergy": allergy,
        "days": days,
        "daily_precip": [daily[d]["precip"] for d in days],
        "daily_count": [daily[d]["count"] for d in days],
        "phenomena": phenomena,
        "wind_rose": wind_rose,
        "statuses": statuses,
        "status_labels": {"draft": "Черновик", "pending": "На проверке",
                          "approved": "Подтверждено", "rework": "Доработка",
                          "rejected": "Отклонено"},
    })


def privacy(request):
    """Страница «Обработка данных и безопасность».

    Учебный проект: персональные реквизиты владельца намеренно не публикуются,
    указывается только дата редакции (PDN_POLICY_UPDATED из настроек).
    """
    from django.conf import settings
    return render(request, "core/privacy.html", {
        "updated_at": settings.PDN_POLICY_UPDATED,
    })

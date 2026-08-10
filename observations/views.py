"""FR-005 внесение, FR-006 модерация, FR-010 доработка, FR-013 история, карта FR-007."""
import json
import uuid as uuid_lib
from django import forms as djforms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404

from core.services import build_weather_warnings, audit
from .forms import ObservationForm, validate_photos
from stations.models import Station
from .weather_owm import WeatherError, fetch_current
from .models import Observation, Photo, Status, PrecipitationType, Phenomenon
from .services import check_anomaly, moderate, resubmit


def observation_create_anon(request):
    """Анонимное наблюдение без регистрации: сохраняется от служебной записи
    «anonymous», помечается в extra и уходит в обычную очередь модерации.
    На карте такие наблюдения выделяются отдельным значком."""
    from accounts.models import User as UserModel
    from .forms import AnonymousObservationForm
    if request.method == "POST":
        form = AnonymousObservationForm(request.POST)
        if form.is_valid():
            obs = form.save(commit=False)
            obs.author = UserModel.get_anonymous_stub()
            obs.status = Status.PENDING
            obs.extra = {"anonymous_submission": True}
            obs.save()
            audit(request, "observation_create_anon", obj=f"observation:{obs.pk}")
            messages.success(request,
                "Спасибо! Анонимное наблюдение отправлено на проверку модератору.")
            return redirect("map")
    else:
        form = AnonymousObservationForm()
    return render(request, "observations/anon_form.html", {"form": form})


def map_view(request):
    """FR-007: главная страница с картой (Leaflet + OpenStreetMap)."""
    from django.contrib.auth import get_user_model
    return render(request, "observations/map.html", {
        "precip_types": PrecipitationType.objects.filter(is_active=True),
        "phenomena": Phenomenon.objects.filter(is_active=True),
        # список аллергенов для фильтра формируется на клиенте из данных карты
        # статистика для боковой панели
        "stat_total": Observation.objects.filter(status=Status.APPROVED,
                                                 is_archived=False).count(),
        "stat_pending": Observation.objects.filter(status=Status.PENDING).count(),
        "stat_observers": get_user_model().objects.filter(
            is_deleted=False, observations__isnull=False).distinct().count(),
        "weather_warnings": build_weather_warnings(),
        "owm_key": settings.OWM_API_KEY,
    })


def api_map_data(request):
    """Данные для карты: только подтверждённые наблюдения публичных точек.
    Лимит 500 точек (ТЗ FR-007), фильтры: период, тип осадков, явления,
    температура, ветер, облачность, наличие фото."""
    from datetime import timedelta
    from django.utils import timezone
    qs = (Observation.objects.filter(status=Status.APPROVED, station__is_public=True,
                                     station__is_active=True, is_archived=False)
          # анонимные наблюдения показываются не дольше 30 дней с внесения
          .exclude(extra__anonymous_submission=True,
                   created_at__lt=timezone.now() - timedelta(days=30))
          .select_related("station", "precipitation_type"))
    g = request.GET
    if g.get("date_from"):
        qs = qs.filter(observed_at__date__gte=g["date_from"])
    if g.get("date_to"):
        qs = qs.filter(observed_at__date__lte=g["date_to"])
    if g.get("precip"):
        qs = qs.filter(precipitation_type__code=g["precip"])
    if g.get("phenomenon"):
        qs = qs.filter(phenomena__code=g["phenomenon"])
    if g.get("t_min"):
        qs = qs.filter(temperature__gte=g["t_min"])
    if g.get("t_max"):
        qs = qs.filter(temperature__lte=g["t_max"])
    if g.get("wind_max"):
        qs = qs.filter(wind_speed__lte=g["wind_max"])
    if g.get("with_photo") == "1":
        qs = qs.filter(photos__isnull=False)
    qs = qs.distinct()[:500]

    # Поля, которых нет у экспресс- и аллергонаблюдений, могут быть пустыми —
    # в сводку берём только заполненные значения
    fnum = lambda v: float(v) if v is not None else None
    feats, temps, press, precip_sum = [], [], [], 0.0
    for o in qs:
        if o.temperature is not None:
            temps.append(float(o.temperature))
        if o.pressure is not None:
            press.append(float(o.pressure))
        precip_sum += float(o.precipitation_amount or 0)
        feats.append({
            "id": o.pk, "station_id": o.station_id,
            "lat": float(o.station.latitude), "lon": float(o.station.longitude),
            "station": o.station.name, "observed_at": o.observed_at.isoformat(),
            "temperature": fnum(o.temperature), "pressure": fnum(o.pressure),
            "obs_type": o.obs_type,
            "pollen": o.get_pollen_level_display() if o.pollen_level else None,
            "allergen": o.allergen.name if o.allergen_id else None,
            "author": o.author.username,
            "anon": bool(o.extra and o.extra.get("anonymous_submission")),
            "wind": fnum(o.wind_speed), "wind_dir": o.wind_direction,
            "water_temp": float(o.water_temperature) if o.water_temperature is not None else None,
            "loc": o.station.location_type,
            "precip": o.precipitation_type.name if o.precipitation_type_id else None,
            "precip_amount": float(o.precipitation_amount or 0), "cloudiness": o.cloudiness,
        })
    summary = None
    if temps:
        summary = {"count": len(temps), "t_min": min(temps), "t_max": max(temps),
                   "t_avg": round(sum(temps) / len(temps), 1),
                   "p_avg": round(sum(press) / len(press), 1) if press else None,
                   "precip_sum": round(precip_sum, 1)}
    # Временные ряды для графиков (ТЗ FR-007: ход температуры и давления,
    # осадки по дням; Chart.js на клиенте)
    series = sorted(feats, key=lambda f: f["observed_at"])
    daily_precip = {}
    for f in series:
        day = f["observed_at"][:10]
        daily_precip[day] = round(daily_precip.get(day, 0) + f["precip_amount"], 1)
    return JsonResponse({"observations": feats, "summary": summary,
                         "series": [{"t": f["observed_at"], "temp": f["temperature"],
                                     "pressure": f["pressure"]} for f in series
                                    if f["temperature"] is not None],
                         "daily_precip": daily_precip})


@login_required
def observation_create(request):
    """FR-005. Поддерживает обычную отправку формы и идемпотентную отправку
    черновика из IndexedDB (заголовок X-Client-UUID / поле client_uuid)."""
    form = ObservationForm(request.POST or None, request.FILES or None, user=request.user)
    if request.method == "POST":
        client_uuid = request.POST.get("client_uuid") or None
        if client_uuid:
            try:
                client_uuid = str(uuid_lib.UUID(client_uuid))   # проверка формата UUID
            except (ValueError, AttributeError, TypeError):
                client_uuid = None
        if client_uuid:
            existing = Observation.objects.filter(client_uuid=client_uuid).first()
            if existing:  # дубликат черновика — возвращаем ранее принятое (ТЗ FR-005)
                if request.headers.get("X-Requested-With") == "fetch":
                    return JsonResponse({"ok": True, "id": existing.pk, "duplicate": True})
                messages.info(request, "Этот черновик уже был отправлен ранее.")
                return redirect("my_observations")
        photos = request.FILES.getlist("photos")
        try:
            validate_photos(photos)
        except djforms.ValidationError as e:
            form.add_error(None, e)
        if form.is_valid():
            obs = form.save(commit=False)
            if obs.station.owner_id != request.user.pk:
                form.add_error("station", "Можно вносить наблюдения только со своих точек.")
            else:
                obs.author = request.user
                obs.status = Status.PENDING
                if client_uuid:
                    obs.client_uuid = uuid_lib.UUID(client_uuid)
                obs = check_anomaly(obs)
                try:
                    obs.save()
                except IntegrityError:
                    messages.info(request, "Этот черновик уже был отправлен ранее.")
                    return redirect("my_observations")
                form.save_m2m()
                for f in photos:
                    Photo.objects.create(observation=obs, image=f, size=f.size)
                audit(request, "observation_create", obj=f"observation:{obs.pk}")
                messages.success(request, "Наблюдение отправлено и поставлено в очередь модерации.")
                if request.headers.get("X-Requested-With") == "fetch":
                    return JsonResponse({"ok": True, "id": obs.pk})
                return redirect("my_observations")
        if request.headers.get("X-Requested-With") == "fetch":
            return JsonResponse({"ok": False, "errors": form.errors}, status=400)
    stations_loc = {st.pk: st.location_type for st in form.fields["station"].queryset}
    return render(request, "observations/form.html",
                  {"form": form, "stations_loc": json.dumps(stations_loc),
                   "weather_enabled": bool(settings.OWM_API_KEY)})


@login_required
def observation_delete(request, pk):
    """Автор может удалить своё наблюдение, пока оно не подтверждено:
    подтверждённые данные — часть общего архива и с карты не убираются
    (их удаляет только администратор через админ-панель)."""
    obs = get_object_or_404(Observation, pk=pk, author=request.user)
    if request.method == "POST":
        if obs.status == Status.APPROVED:
            messages.error(request,
                "Подтверждённое наблюдение удалить нельзя — обратитесь к администратору.")
        else:
            audit(request, "observation_delete", obj=f"observation:{obs.pk}")
            obs.delete()
            messages.success(request, "Наблюдение удалено.")
    return redirect("my_observations")


@login_required
def my_observations(request):
    """FR-013: история собственных наблюдений со статусами и комментариями."""
    qs = (request.user.observations.filter(is_archived=False)
          .select_related("station", "precipitation_type").order_by("-observed_at"))
    status = request.GET.get("status")
    if status:
        qs = qs.filter(status=status)
    page = Paginator(qs, 20).get_page(request.GET.get("page"))
    return render(request, "observations/my_list.html",
                  {"page": page, "statuses": Status.choices, "cur_status": status,
                   "max_resubmits": settings.OBSERVATION_MAX_RESUBMITS})


@login_required
def observation_rework(request, pk):
    """FR-010: доработка возвращённого наблюдения (только статус rework, лимит 3)."""
    obs = get_object_or_404(Observation, pk=pk, author=request.user)
    if obs.status != Status.REWORK:
        messages.error(request, "Редактировать можно только наблюдения в статусе «Доработка».")
        return redirect("my_observations")
    if obs.resubmit_count >= settings.OBSERVATION_MAX_RESUBMITS:
        messages.error(request, "Исчерпан лимит повторных отправок (3). Доступна апелляция администратору.")
        return redirect("my_observations")
    form = ObservationForm(request.POST or None, instance=obs, user=request.user)
    last_comment = obs.moderation_log.exclude(comment="").first()
    if request.method == "POST" and form.is_valid():
        obs = form.save(commit=False)
        resubmit(request, obs)
        form.save_m2m()
        messages.success(request, "Наблюдение доработано и повторно отправлено на модерацию.")
        return redirect("my_observations")
    stations_loc = {st.pk: st.location_type for st in form.fields["station"].queryset}
    return render(request, "observations/form.html",
                  {"form": form, "rework": obs, "last_comment": last_comment,
                   "stations_loc": json.dumps(stations_loc),
                   "weather_enabled": bool(settings.OWM_API_KEY)})


def _is_moderator(user):
    return user.is_authenticated and user.is_moderator


@user_passes_test(_is_moderator)
def moderation_queue(request):
    """FR-006: очередь наблюдений «На проверке»."""
    qs = (Observation.objects.filter(status=Status.PENDING)
          .select_related("station", "author", "precipitation_type")
          .order_by("created_at"))
    page = Paginator(qs, 20).get_page(request.GET.get("page"))
    return render(request, "observations/moderation_queue.html", {"page": page})


@user_passes_test(_is_moderator)
def moderation_detail(request, pk):
    obs = get_object_or_404(
        Observation.objects.select_related("station", "author", "precipitation_type"), pk=pk)
    if request.method == "POST":
        decision = request.POST.get("decision")
        comment = request.POST.get("comment", "").strip()
        if decision not in ("approve", "reject", "rework"):
            messages.error(request, "Неизвестное решение.")
        elif decision in ("reject", "rework") and not comment:
            messages.error(request, "Комментарий обязателен при отклонении и доработке.")
        elif obs.status != Status.PENDING:
            messages.error(request, "Наблюдение уже обработано.")
        else:
            moderate(request, obs, decision, comment)
            messages.success(request, "Решение сохранено, автор уведомлён.")
            return redirect("moderation_queue")
    return render(request, "observations/moderation_detail.html", {"obs": obs})


@login_required
def api_weather_prefill(request):
    """Текущая погода по координатам точки — для кнопки «Подставить погоду».

    Точка должна принадлежать пользователю: иначе через этот эндпоинт можно
    было бы бесплатно пользоваться нашим ключом для произвольных координат.
    """
    station_id = request.GET.get("station")
    station = Station.objects.filter(pk=station_id, owner=request.user).first()
    if not station:
        return JsonResponse({"ok": False, "error": "Точка не найдена."}, status=404)
    try:
        data = fetch_current(station.latitude, station.longitude)
    except WeatherError as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=502)
    return JsonResponse({"ok": True, "data": data})

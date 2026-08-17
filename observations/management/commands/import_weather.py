"""Импорт текущей погоды из OpenWeatherMap в наблюдения.

Назначение: наполнить карту и отчёты реальными метеоданными по точкам
наблюдения. Запускается вручную или по расписанию (cron / celery beat).

ВАЖНО о происхождении данных:
записи создаются от имени служебного пользователя «Метеослужба (автоимпорт)»,
а в поле extra проставляется source="openweathermap". Это сделано намеренно,
чтобы автоматически импортированные данные нельзя было спутать с замерами
живых наблюдателей: их видно и в админке, и в выгрузке отчётов.

Примеры:
    python manage.py import_weather                # все активные точки
    python manage.py import_weather --limit 10     # только первые 10
    python manage.py import_weather --dry-run      # показать, ничего не писать
    python manage.py import_weather --create-cities  # создать точки по городам
"""
import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

# Крупные города России: используются с ключом --create-cities, чтобы было
# откуда брать погоду, если своих точек ещё нет.
CITIES = [
    ("Москва", 55.7558, 37.6176, 156),
    ("Санкт-Петербург", 59.9311, 30.3609, 3),
    ("Новосибирск", 55.0084, 82.9357, 150),
    ("Екатеринбург", 56.8389, 60.6057, 270),
    ("Казань", 55.7963, 49.1088, 60),
    ("Нижний Новгород", 56.3269, 44.0059, 78),
    ("Челябинск", 55.1644, 61.4368, 220),
    ("Самара", 53.1959, 50.1002, 100),
    ("Ростов-на-Дону", 47.2225, 39.7187, 75),
    ("Уфа", 54.7388, 55.9721, 130),
    ("Красноярск", 56.0184, 92.8672, 140),
    ("Воронеж", 51.6720, 39.1843, 154),
    ("Пермь", 58.0105, 56.2502, 120),
    ("Волгоград", 48.7080, 44.5133, 50),
    ("Иркутск", 52.2870, 104.3050, 440),
    ("Владивосток", 43.1155, 131.8855, 30),
    ("Мурманск", 68.9585, 33.0827, 50),
    ("Сочи", 43.6028, 39.7342, 30),
    ("Архангельск", 64.5393, 40.5169, 7),
    ("Якутск", 62.0355, 129.6755, 100),
]

SERVICE_USERNAME = "weather_service"


class Command(BaseCommand):
    help = "Импортирует текущую погоду из OpenWeatherMap в наблюдения"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=0,
                            help="ограничить число точек (0 — все)")
        parser.add_argument("--dry-run", action="store_true",
                            help="показать, что было бы импортировано, ничего не записывая")
        parser.add_argument("--create-cities", action="store_true",
                            help="создать точки наблюдения по списку крупных городов")
        parser.add_argument("--delay", type=float, default=1.2,
                            help="пауза между запросами к API, секунд (бесплатный тариф: 60 запросов/мин)")

    def handle(self, *args, **opts):
        from accounts.models import User
        from stations.models import Station
        from observations.models import Observation, ObsType, Status, PrecipitationType
        from observations.weather_owm import fetch_current, WeatherError

        if not settings.OWM_API_KEY:
            self.stderr.write(self.style.ERROR(
                "OWM_API_KEY не задан. Пропишите ключ в .env и повторите."))
            return

        dry = opts["dry_run"]

        # Служебный аккаунт: вход под ним невозможен, он лишь помечает
        # автоматически импортированные записи.
        service, created = User.objects.get_or_create(
            username=SERVICE_USERNAME,
            defaults={"first_name": "Метеослужба", "last_name": "(автоимпорт)",
                      "email": None, "is_active": False},
        )
        if created:
            service.set_unusable_password()
            service.save()
            self.stdout.write(f"Создан служебный пользователь «{SERVICE_USERNAME}»")

        if opts["create_cities"] and not dry:
            made = 0
            for name, lat, lon, height in CITIES:
                _, was_created = Station.objects.get_or_create(
                    owner=service, name=name,
                    defaults={"latitude": lat, "longitude": lon, "height": height,
                              "location_type": "inland", "is_public": True,
                              "description": "Точка автоматического импорта погоды"},
                )
                made += int(was_created)
            self.stdout.write(f"Точек создано: {made} (всего в списке: {len(CITIES)})")

        stations = list(Station.objects.filter(is_active=True).order_by("id"))
        if opts["limit"]:
            stations = stations[:opts["limit"]]
        if not stations:
            self.stderr.write(self.style.WARNING(
                "Активных точек нет. Запустите с --create-cities."))
            return

        # тип осадков подбираем по факту: есть осадки или нет
        rain = PrecipitationType.objects.filter(code="rain").first()
        snow = PrecipitationType.objects.filter(code="snow").first()
        none_p = PrecipitationType.objects.filter(code="none").first()

        ok = skipped = failed = 0
        now = timezone.now()

        for st in stations:
            try:
                data = fetch_current(st.latitude, st.longitude)
            except WeatherError as e:
                failed += 1
                self.stderr.write(f"  {st.name}: {e}")
                time.sleep(opts["delay"])
                continue

            if data.get("temperature") is None:
                skipped += 1
                continue

            precip_amount = data.get("precipitation_amount") or 0
            if precip_amount > 0:
                ptype = snow if data["temperature"] <= 0 else rain
            else:
                ptype = none_p

            line = (f"  {st.name}: {data['temperature']} °C, "
                    f"{data.get('pressure')} гПа, ветер {data.get('wind_speed')} м/с, "
                    f"облачность {data.get('cloudiness')}%")

            if dry:
                self.stdout.write(line + "  [dry-run]")
                ok += 1
                time.sleep(opts["delay"])
                continue

            # Защита от дублей: если по этой точке уже есть импорт за последний
            # час, повторную запись не создаём.
            recent = Observation.objects.filter(
                station=st, author=service,
                observed_at__gte=now - timezone.timedelta(hours=1)).exists()
            if recent:
                skipped += 1
                time.sleep(opts["delay"])
                continue

            with transaction.atomic():
                Observation.objects.create(
                    station=st, author=service, observed_at=now,
                    obs_type=ObsType.FULL,
                    temperature=data["temperature"],
                    pressure=data.get("pressure"),
                    wind_speed=data.get("wind_speed"),
                    wind_direction=data.get("wind_direction") or "",
                    cloudiness=data.get("cloudiness"),
                    precipitation_amount=precip_amount,
                    precipitation_type=ptype,
                    # автоимпорт публикуем сразу: данные пришли от метеосервиса
                    # и в модерации человеком не нуждаются
                    status=Status.APPROVED,
                    moderated_at=now,
                    extra={"source": "openweathermap",
                           "imported_at": now.isoformat(),
                           "description": data.get("description", "")},
                )
            ok += 1
            self.stdout.write(line)
            time.sleep(opts["delay"])

        self.stdout.write(self.style.SUCCESS(
            f"Готово. Импортировано: {ok}, пропущено: {skipped}, ошибок: {failed}"))

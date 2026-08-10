"""Наполнение справочников (ТЗ 4.7.1) и демо-данных: python manage.py seed"""
from datetime import timedelta
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Справочники и демо-данные"

    def handle(self, *args, **kw):
        from accounts.models import User, Roles
        from stations.models import Station
        from observations.models import (Allergen, ObsType, Phenomenon,
                                         PollenLevel, PrecipitationType,
                                         Observation, Status)
        for code, name in [("rain", "Дождь"), ("snow", "Снег"),
                           ("hail", "Град"), ("none", "Отсутствие осадков")]:
            PrecipitationType.objects.get_or_create(code=code, defaults={"name": name})
        # справочник аллергенов для аллергонаблюдений
        for code, name in [("birch", "Берёза"), ("grass", "Злаковые травы"),
                           ("wormwood", "Полынь"), ("ragweed", "Амброзия"),
                           ("poplar", "Тополиный пух"), ("mold", "Споры плесени")]:
            Allergen.objects.get_or_create(code=code, defaults={"name": name})
        for code, name in [("fog", "Туман"), ("storm", "Гроза"),
                           ("blizzard", "Метель"), ("rainbow", "Радуга")]:
            Phenomenon.objects.get_or_create(code=code, defaults={"name": name})
        User.get_anonymous_stub()

        def mkuser(username, role, superuser=False):
            u, created = User.objects.get_or_create(
                username=username,
                defaults={"role": role, "email": f"{username}@example.com",
                          "consent_at": timezone.now(),
                          "is_staff": superuser, "is_superuser": superuser})
            if created:
                u.set_password("sinoptik123")
                u.save()
            return u

        admin = mkuser("admin", Roles.ADMIN, superuser=True)
        moder = mkuser("moderator", Roles.MODERATOR)
        obs_user = mkuser("observer", Roles.OBSERVER)

        st, _ = Station.objects.get_or_create(
            owner=obs_user, name="Усть-Кулом, школа №1",
            defaults={"latitude": Decimal("61.686000"), "longitude": Decimal("53.690000"),
                      "height": 120, "equipment": "термометр ТМ-4, барометр-анероид"})
        st2, _ = Station.objects.get_or_create(
            owner=obs_user, name="Троицко-Печорск, метеоплощадка",
            defaults={"latitude": Decimal("62.708000"), "longitude": Decimal("56.196000"),
                      "height": 135})

        snow = PrecipitationType.objects.get(code="snow")
        none_p = PrecipitationType.objects.get(code="none")
        now = timezone.now().replace(minute=0, second=0, microsecond=0)
        demo = [
            (st, now - timedelta(days=2), "-4.5", "998.0", "3.2", "NW", "1.2", snow, 80, Status.APPROVED),
            (st, now - timedelta(days=1), "-6.0", "1002.5", "2.0", "N", "0.4", snow, 60, Status.APPROVED),
            (st2, now - timedelta(days=1, hours=2), "-5.1", "1001.0", "4.5", "NNW", "0.0", none_p, 40, Status.APPROVED),
            (st, now - timedelta(hours=3), "-3.2", "996.0", "5.0", "W", "2.1", snow, 90, Status.PENDING),
        ]
        for station, dt, t, p, w, wd, pa, pt, cl, status in demo:
            o, created = Observation.objects.get_or_create(
                station=station, observed_at=dt,
                defaults={"author": obs_user, "temperature": Decimal(t),
                          "pressure": Decimal(p), "wind_speed": Decimal(w),
                          "wind_direction": wd, "precipitation_amount": Decimal(pa),
                          "precipitation_type": pt, "cloudiness": cl, "status": status,
                          "moderator": moder if status == Status.APPROVED else None,
                          "moderated_at": dt if status == Status.APPROVED else None})

        # --- Демо-сеть точек по всей России: 50 станций, у каждой 5–12
        # наблюдений за последние 30 дней. Климат упрощённо зависит от широты,
        # для прибрежных и островных точек генерируется температура воды.
        import math
        import random
        rnd = random.Random(42)                    # фиксированное зерно — данные воспроизводимы
        rain = PrecipitationType.objects.get(code="rain")
        fog = Phenomenon.objects.get(code="fog")
        storm = Phenomenon.objects.get(code="storm")
        RUMBS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                 "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
        WEIGHTS = [2, 1, 1, 1, 2, 1, 2, 3, 4, 6, 9, 8, 7, 4, 3, 2]  # преобладание ЮЗ/З
        # (название, широта, долгота, высота, тип местности)
        CITIES = [
            ("Москва, Останкино", 55.82, 37.61, 160, "inland"),
            ("Санкт-Петербург, Васильевский остров", 59.94, 30.25, 5, "coast"),
            ("Калининград, набережная", 54.71, 20.45, 8, "coast"),
            ("Мурманск, залив", 68.97, 33.08, 30, "coast"),
            ("Архангельск, Двина", 64.55, 40.53, 10, "coast"),
            ("Петрозаводск, Онего", 61.79, 34.36, 45, "coast"),
            ("Вологда", 59.22, 39.89, 120, "inland"),
            ("Ярославль", 57.63, 39.87, 100, "inland"),
            ("Нижний Новгород, стрелка", 56.33, 44.00, 78, "inland"),
            ("Казань, Кремль", 55.80, 49.11, 60, "inland"),
            ("Самара, набережная", 53.20, 50.11, 45, "inland"),
            ("Саратов", 51.53, 46.03, 55, "inland"),
            ("Волгоград", 48.71, 44.51, 40, "inland"),
            ("Астрахань, дельта", 46.35, 48.04, -20, "coast"),
            ("Ростов-на-Дону", 47.23, 39.72, 70, "inland"),
            ("Краснодар", 45.04, 38.98, 25, "inland"),
            ("Сочи, морвокзал", 43.58, 39.72, 5, "coast"),
            ("Новороссийск, бухта", 44.72, 37.77, 10, "coast"),
            ("Севастополь, Херсонес", 44.61, 33.49, 20, "coast"),
            ("Симферополь", 44.95, 34.10, 250, "inland"),
            ("Воронеж", 51.66, 39.20, 150, "inland"),
            ("Белгород", 50.60, 36.59, 150, "inland"),
            ("Курск", 51.73, 36.19, 220, "inland"),
            ("Тула", 54.19, 37.62, 170, "inland"),
            ("Смоленск", 54.78, 32.05, 240, "inland"),
            ("Псков", 57.82, 28.33, 45, "inland"),
            ("Киров", 58.60, 49.66, 150, "inland"),
            ("Пермь, Кама", 58.01, 56.25, 150, "inland"),
            ("Сыктывкар, центр", 61.67, 50.84, 100, "inland"),
            ("Уфа", 54.73, 55.97, 160, "inland"),
            ("Оренбург", 51.77, 55.10, 110, "inland"),
            ("Екатеринбург, Уралмаш", 56.89, 60.61, 250, "inland"),
            ("Челябинск", 55.16, 61.40, 220, "inland"),
            ("Тюмень", 57.15, 65.53, 80, "inland"),
            ("Омск, Иртыш", 54.99, 73.37, 90, "inland"),
            ("Новосибирск, Обь", 55.01, 82.93, 120, "inland"),
            ("Томск", 56.50, 84.97, 120, "inland"),
            ("Барнаул", 53.35, 83.78, 180, "inland"),
            ("Красноярск, Енисей", 56.01, 92.87, 140, "inland"),
            ("Иркутск, Ангара", 52.29, 104.28, 440, "inland"),
            ("Листвянка, Байкал", 51.85, 104.87, 460, "coast"),
            ("Улан-Удэ", 51.83, 107.58, 510, "inland"),
            ("Чита", 52.03, 113.50, 650, "inland"),
            ("Якутск, Лена", 62.03, 129.73, 100, "inland"),
            ("Норильск", 69.35, 88.20, 60, "inland"),
            ("Салехард, Обская губа", 66.53, 66.60, 15, "coast"),
            ("Хабаровск, Амур", 48.48, 135.08, 70, "inland"),
            ("Владивосток, Золотой Рог", 43.12, 131.89, 10, "coast"),
            ("Южно-Сахалинск, о. Сахалин", 46.96, 142.74, 20, "island"),
            ("Петропавловск-Камчатский, Авачинская бухта", 53.02, 158.65, 15, "coast"),
        ]
        made = 0
        for name, lat, lon, h, loc in CITIES:
            station, _ = Station.objects.get_or_create(
                owner=obs_user, name=name,
                defaults={"latitude": Decimal(f"{lat:.6f}"),
                          "longitude": Decimal(f"{lon:.6f}"),
                          "height": h, "location_type": loc})
            if station.observations.exists():
                continue                            # повторный запуск — не дублируем
            # упрощённый климат: теплее к югу (широта 43…70 -> +14…-6 °C летом)
            climate_t = 24 - (lat - 43) * 0.75
            n_obs = rnd.randint(5, 12)
            for _ in range(n_obs):
                dt = now - timedelta(days=rnd.uniform(0.2, 30),
                                     minutes=rnd.randint(0, 59))
                hour = dt.hour
                t = (climate_t + 5 * math.sin((hour - 4) / 24 * 2 * math.pi)
                     + rnd.uniform(-3, 3))
                p = 1005 + rnd.uniform(-12, 10) - h / 32   # барометрическая поправка
                p = max(920.0, p)
                wind = max(0.0, rnd.gauss(4, 2.4))
                wd = "" if wind < 0.5 else rnd.choices(RUMBS, weights=WEIGHTS)[0]
                rainy = rnd.random() < 0.3
                pa = round(rnd.uniform(0.5, 9.0), 1) if rainy else 0.0
                ptype = (rain if t > 0 else snow) if rainy else none_p
                wt = None
                if loc in ("coast", "island"):
                    wt = Decimal(f"{max(0.5, t * 0.55 + 3 + rnd.uniform(-1, 1)):.1f}")
                o = Observation.objects.create(
                    station=station, author=obs_user, observed_at=dt,
                    temperature=Decimal(f"{t:.1f}"), pressure=Decimal(f"{p:.1f}"),
                    wind_speed=Decimal(f"{wind:.1f}"), wind_direction=wd,
                    precipitation_amount=Decimal(f"{pa:.1f}"),
                    precipitation_type=ptype, water_temperature=wt,
                    cloudiness=rnd.choice((10, 30, 50, 70, 90, 100)),
                    status=Status.APPROVED, moderator=moder, moderated_at=dt)
                if rainy and wind > 6:
                    o.phenomena.add(storm)
                elif hour in (6, 7, 8) and rnd.random() < 0.25:
                    o.phenomena.add(fog)
                made += 1
        # Анонимные демо-наблюдения: 14 свежих замеров (в пределах 30-дневного
        # срока хранения) от случайных публичных точек + помечаем анонимными
        # три уже существующих — на карте видно выделение серым маркером
        anon_stub = User.get_anonymous_stub()
        for o in Observation.objects.filter(status=Status.APPROVED).order_by("?")[:3]:
            o.author = anon_stub
            o.extra = {"anonymous_submission": True}
            o.save(update_fields=["author", "extra"])
        pub_stations = list(Station.objects.filter(is_active=True, is_public=True))
        for _ in range(14):
            station = rnd.choice(pub_stations)
            dt = now - timedelta(days=rnd.uniform(0.1, 20), minutes=rnd.randint(0, 59))
            t = 24 - (float(station.latitude) - 43) * 0.75 + rnd.uniform(-4, 4)
            wind = max(0.0, rnd.gauss(4, 2.4))
            rainy = rnd.random() < 0.3
            Observation.objects.create(
                station=station, author=anon_stub, observed_at=dt,
                temperature=Decimal(f"{t:.1f}"),
                pressure=Decimal(f"{1005 + rnd.uniform(-10, 8):.1f}"),
                wind_speed=Decimal(f"{wind:.1f}"),
                wind_direction="" if wind < 0.5 else rnd.choices(RUMBS, weights=WEIGHTS)[0],
                precipitation_amount=Decimal(f"{rnd.uniform(0.5, 7.0):.1f}" if rainy else "0.0"),
                precipitation_type=(rain if t > 0 else snow) if rainy else none_p,
                cloudiness=rnd.choice((10, 30, 50, 70, 90, 100)),
                status=Status.APPROVED, moderator=moder, moderated_at=dt,
                extra={"anonymous_submission": True})

        # Демо-аллергонаблюдения: без них на карте нет пыльцевых меток,
        # пустует аллергосводка на дашборде и не срабатывают предупреждения.
        # Раскидываем свежие замеры (в пределах 30-дневного окна) по случайным
        # точкам; часть — с высоким/очень высоким уровнем за последние сутки,
        # чтобы были видны и метки, и предупреждения об аллергии.
        allergy_made = 0
        if not Observation.objects.filter(obs_type=ObsType.ALLERGY).exists():
            allergens = list(Allergen.objects.filter(is_active=True))
            all_stations = list(Station.objects.filter(is_active=True))
            # уровни пыльцы: числовое значение облачности/ветра тут не нужно,
            # аллергонаблюдению достаточно уровня и (по желанию) аллергена
            LEVELS = [PollenLevel.LOW, PollenLevel.MEDIUM,
                      PollenLevel.HIGH, PollenLevel.VERY_HIGH]
            # свежие «высокие» замеры за последние сутки — для предупреждений
            recent_high = [
                (rnd.choice(all_stations), PollenLevel.VERY_HIGH),
                (rnd.choice(all_stations), PollenLevel.HIGH),
                (rnd.choice(all_stations), PollenLevel.HIGH),
            ]
            for station, level in recent_high:
                dt = now - timedelta(hours=rnd.uniform(1, 20))
                t = 24 - (float(station.latitude) - 43) * 0.75 + rnd.uniform(-3, 3)
                Observation.objects.create(
                    station=station, author=obs_user, observed_at=dt,
                    obs_type=ObsType.ALLERGY, pollen_level=level,
                    allergen=rnd.choice(allergens),
                    temperature=Decimal(f"{t:.1f}"),
                    wind_speed=Decimal(f"{max(0.0, rnd.gauss(3, 1.5)):.1f}"),
                    cloudiness=rnd.choice((10, 30, 50)),
                    precipitation_amount=Decimal("0.0"), precipitation_type=none_p,
                    status=Status.APPROVED, moderator=moder, moderated_at=dt)
                allergy_made += 1
            # ещё 16 замеров с разными уровнями за последний месяц —
            # наполняют график динамики пыльцы и топ аллергенов
            for _ in range(16):
                station = rnd.choice(all_stations)
                dt = now - timedelta(days=rnd.uniform(0.5, 29),
                                     minutes=rnd.randint(0, 59))
                # чем ближе к «сезону», тем чаще высокий уровень
                level = rnd.choices(LEVELS, weights=[3, 4, 3, 2])[0]
                t = 24 - (float(station.latitude) - 43) * 0.75 + rnd.uniform(-4, 4)
                Observation.objects.create(
                    station=station, author=obs_user, observed_at=dt,
                    obs_type=ObsType.ALLERGY, pollen_level=level,
                    allergen=rnd.choice(allergens) if rnd.random() < 0.85 else None,
                    temperature=Decimal(f"{t:.1f}"),
                    wind_speed=Decimal(f"{max(0.0, rnd.gauss(3, 1.6)):.1f}"),
                    cloudiness=rnd.choice((10, 30, 50, 70)),
                    precipitation_amount=Decimal("0.0"), precipitation_type=none_p,
                    status=Status.APPROVED, moderator=moder, moderated_at=dt)
                allergy_made += 1

        if made:
            self.stdout.write(f"Создано точек: {len(CITIES)}, демо-наблюдений: {made}")
        if allergy_made:
            self.stdout.write(f"Создано аллергонаблюдений: {allergy_made}")
        self.stdout.write(self.style.SUCCESS(
            "Готово. Пользователи: admin / moderator / observer, пароль: sinoptik123"))

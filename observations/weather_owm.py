"""Подстановка текущей погоды в форму наблюдения через OpenWeatherMap.

Наблюдатель нажимает «Подставить текущую погоду» — сервис запрашивает данные
по координатам его точки и заполняет поля формы. Значения остаются
редактируемыми: это подсказка, а не замена собственного замера.

Используется тот же ключ OWM_API_KEY, что и для слоя осадков на карте.
Документация: https://openweathermap.org/current
"""
import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

log = logging.getLogger(__name__)


class WeatherError(Exception):
    """Понятная пользователю ошибка обращения к сервису погоды."""


# 16 румбов по градусам направления ветра (meteorological — откуда дует)
_DIRS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
         "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]


def fetch_current(latitude, longitude):
    """Текущая погода по координатам через OpenWeatherMap.

    Возвращает словарь полей наблюдения. Бросает WeatherError с русским
    текстом — его можно показать пользователю как есть.
    """
    if not settings.OWM_API_KEY:
        raise WeatherError("Ключ OpenWeatherMap не задан в настройках.")

    url = "https://api.openweathermap.org/data/2.5/weather?" + urllib.parse.urlencode({
        "lat": f"{float(latitude):.4f}", "lon": f"{float(longitude):.4f}",
        "appid": settings.OWM_API_KEY, "units": "metric", "lang": "ru"})
    try:
        with urllib.request.urlopen(url, timeout=settings.WEATHER_TIMEOUT) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        log.warning("OWM HTTP %s", e.code)
        if e.code == 401:
            raise WeatherError("Ключ OpenWeatherMap не активирован "
                               "(до 2 часов после регистрации).")
        raise WeatherError(f"Сервис погоды ответил ошибкой {e.code}.")
    except (urllib.error.URLError, TimeoutError):
        raise WeatherError("Сервис погоды недоступен — попробуйте позже.")
    except (ValueError, json.JSONDecodeError):
        raise WeatherError("Сервис погоды вернул неожиданный ответ.")

    return parse_current(payload)


def parse_current(payload):
    """Ответ OpenWeatherMap → поля формы. Вынесено отдельно для тестов."""
    main = (payload or {}).get("main") or {}
    wind = (payload or {}).get("wind") or {}
    clouds = (payload or {}).get("clouds") or {}
    weather = (payload or {}).get("weather") or [{}]
    if not main:
        raise WeatherError("В ответе сервиса нет данных о погоде.")

    deg = wind.get("deg")
    direction = _DIRS[round(deg / 22.5) % 16] if deg is not None else ""
    # осадки за последний час (дождь или снег), если сервис их вернул
    precip = 0.0
    for key in ("rain", "snow"):
        block = payload.get(key) or {}
        precip += float(block.get("1h") or block.get("3h") or 0)

    return {
        "temperature": round(float(main["temp"]), 1) if main.get("temp") is not None else None,
        "pressure": float(main["pressure"]) if main.get("pressure") is not None else None,
        "wind_speed": round(float(wind["speed"]), 1) if wind.get("speed") is not None else None,
        "wind_direction": direction,
        "cloudiness": int(clouds["all"]) if clouds.get("all") is not None else None,
        "precipitation_amount": round(precip, 1),
        "description": (weather[0].get("description") or "").capitalize(),
        "source": "OpenWeatherMap",
    }


# --- Прогноз и поиск городов ----------------------------------------------
# Используется разделом «Погода»: поиск места по названию, текущая погода и
# прогноз на 5 суток. Все ответы кэшируются, чтобы не упираться в лимит
# бесплатного тарифа OpenWeatherMap (60 запросов в минуту).

from django.core.cache import cache

CACHE_CURRENT = 10 * 60      # текущая погода — 10 минут
CACHE_FORECAST = 30 * 60     # прогноз — полчаса, он и так трёхчасовой
CACHE_GEO = 24 * 3600        # координаты города меняться не будут


def geocode(query, limit=5):
    """Ищет место по названию. Возвращает список словарей с координатами."""
    if not settings.OWM_API_KEY:
        raise WeatherError("Ключ OpenWeatherMap не задан в настройках.")
    query = (query or "").strip()
    if len(query) < 2:
        return []

    key = f"owm:geo:{query.lower()}:{limit}"
    cached = cache.get(key)
    if cached is not None:
        return cached

    url = "https://api.openweathermap.org/geo/1.0/direct?" + urllib.parse.urlencode({
        "q": query, "limit": limit, "appid": settings.OWM_API_KEY})
    try:
        with urllib.request.urlopen(url, timeout=settings.WEATHER_TIMEOUT) as resp:
            rows = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise WeatherError(f"Сервис поиска ответил ошибкой {e.code}.")
    except (urllib.error.URLError, TimeoutError):
        raise WeatherError("Сервис поиска недоступен — попробуйте позже.")
    except (ValueError, json.JSONDecodeError):
        raise WeatherError("Сервис поиска вернул неожиданный ответ.")

    places = []
    for r in rows or []:
        # предпочитаем русское название, если оно есть
        name = (r.get("local_names") or {}).get("ru") or r.get("name") or ""
        places.append({
            "name": name,
            "country": r.get("country", ""),
            "state": (r.get("local_names") or {}).get("ru_state") or r.get("state", ""),
            "lat": round(float(r["lat"]), 4),
            "lon": round(float(r["lon"]), 4),
        })
    cache.set(key, places, CACHE_GEO)
    return places


def current_cached(lat, lon):
    """Текущая погода с кэшем — чтобы повторные открытия страницы не
    расходовали лимит запросов."""
    key = f"owm:cur:{round(float(lat), 3)}:{round(float(lon), 3)}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    data = fetch_current(lat, lon)
    cache.set(key, data, CACHE_CURRENT)
    return data


def forecast(lat, lon, days=5):
    """Прогноз на несколько суток (бесплатный тариф OWM: 5 дней, шаг 3 часа).

    Возвращает список дней: дата, минимальная и максимальная температура,
    преобладающее описание, осадки за сутки и почасовые точки.
    """
    if not settings.OWM_API_KEY:
        raise WeatherError("Ключ OpenWeatherMap не задан в настройках.")

    key = f"owm:fc:{round(float(lat), 3)}:{round(float(lon), 3)}"
    cached = cache.get(key)
    if cached is not None:
        return cached

    url = "https://api.openweathermap.org/data/2.5/forecast?" + urllib.parse.urlencode({
        "lat": f"{float(lat):.4f}", "lon": f"{float(lon):.4f}",
        "appid": settings.OWM_API_KEY, "units": "metric", "lang": "ru"})
    try:
        with urllib.request.urlopen(url, timeout=settings.WEATHER_TIMEOUT) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise WeatherError("Ключ OpenWeatherMap не активирован.")
        raise WeatherError(f"Сервис прогноза ответил ошибкой {e.code}.")
    except (urllib.error.URLError, TimeoutError):
        raise WeatherError("Сервис прогноза недоступен — попробуйте позже.")
    except (ValueError, json.JSONDecodeError):
        raise WeatherError("Сервис прогноза вернул неожиданный ответ.")

    result = _group_forecast(payload, days)
    cache.set(key, result, CACHE_FORECAST)
    return result


def _group_forecast(payload, days=5):
    """Трёхчасовые точки OWM → сводка по суткам. Вынесено для тестов."""
    from collections import defaultdict

    by_day = defaultdict(list)
    for item in (payload or {}).get("list", []):
        day = item.get("dt_txt", "")[:10]     # «2026-08-21 15:00:00» → дата
        if day:
            by_day[day].append(item)

    out = []
    for day in sorted(by_day)[:days]:
        points = by_day[day]
        temps = [p["main"]["temp"] for p in points if p.get("main")]
        if not temps:
            continue
        # преобладающее описание за день — то, что встречается чаще
        descr = {}
        for p in points:
            d = ((p.get("weather") or [{}])[0].get("description") or "").capitalize()
            if d:
                descr[d] = descr.get(d, 0) + 1
        precip = sum(float((p.get("rain") or {}).get("3h", 0))
                     + float((p.get("snow") or {}).get("3h", 0)) for p in points)
        winds = [p.get("wind", {}).get("speed") for p in points
                 if p.get("wind", {}).get("speed") is not None]

        out.append({
            "date": day,
            "t_min": round(min(temps), 1),
            "t_max": round(max(temps), 1),
            "description": max(descr, key=descr.get) if descr else "",
            "precip": round(precip, 1),
            "wind": round(max(winds), 1) if winds else None,
            "hours": [{
                "time": p["dt_txt"][11:16],
                "temp": round(p["main"]["temp"], 1),
                "descr": ((p.get("weather") or [{}])[0].get("description") or "").capitalize(),
            } for p in points],
        })
    return out

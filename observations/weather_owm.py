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

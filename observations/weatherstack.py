"""Интеграция с Weatherstack: подстановка текущей погоды в форму наблюдения.

Наблюдатель нажимает «Подставить текущую погоду» — сервис запрашивает
данные по координатам его точки и заполняет поля формы. Значения остаются
редактируемыми: это подсказка, а не замена собственного замера.

Документация: https://docs.apilayer.com/weatherstack/docs/quickstart-guide
"""
import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

log = logging.getLogger(__name__)

# румбы Weatherstack (N, ENE, …) совпадают с кодами в модели Observation
KNOWN_DIRECTIONS = {"N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"}


class WeatherstackError(Exception):
    """Понятная пользователю ошибка обращения к сервису."""


def _build_request(query):
    """Возвращает Request для выбранного режима (прямой или через apilayer)."""
    if settings.WEATHERSTACK_MODE == "apilayer":
        url = "https://api.apilayer.com/weatherstack/current?" + urllib.parse.urlencode(
            {"query": query, "units": "m"})
        return urllib.request.Request(url, headers={"apikey": settings.WEATHERSTACK_KEY})
    # прямой доступ: на бесплатном тарифе weatherstack доступен только HTTP
    url = "http://api.weatherstack.com/current?" + urllib.parse.urlencode(
        {"access_key": settings.WEATHERSTACK_KEY, "query": query, "units": "m"})
    return urllib.request.Request(url)


def fetch_current(latitude, longitude):
    """Текущая погода по координатам. Возвращает словарь полей наблюдения.

    Бросает WeatherstackError с русским текстом — его можно показать
    пользователю как есть.
    """
    if not settings.WEATHERSTACK_KEY:
        raise WeatherstackError("Ключ Weatherstack не задан в настройках.")

    query = f"{float(latitude):.4f},{float(longitude):.4f}"
    try:
        with urllib.request.urlopen(_build_request(query),
                                    timeout=settings.WEATHERSTACK_TIMEOUT) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        log.warning("Weatherstack HTTP %s", e.code)
        raise WeatherstackError(f"Сервис погоды ответил ошибкой {e.code}.")
    except (urllib.error.URLError, TimeoutError) as e:
        log.warning("Weatherstack недоступен: %s", e)
        raise WeatherstackError("Сервис погоды недоступен — попробуйте позже.")
    except (ValueError, json.JSONDecodeError):
        raise WeatherstackError("Сервис погоды вернул неожиданный ответ.")

    # Weatherstack отдаёт ошибки со статусом 200 и полем "error"
    if isinstance(payload, dict) and payload.get("error"):
        info = payload["error"].get("info") or "неизвестная ошибка"
        log.warning("Weatherstack error: %s", info)
        raise WeatherstackError(f"Сервис погоды: {info}")

    return parse_current(payload)


def parse_current(payload):
    """Ответ API → поля формы. Вынесено отдельно, чтобы тестировать без сети."""
    cur = (payload or {}).get("current") or {}
    if not cur:
        raise WeatherstackError("В ответе сервиса нет данных о погоде.")

    def num(key):
        v = cur.get(key)
        return None if v in (None, "") else float(v)

    direction = (cur.get("wind_dir") or "").upper()
    data = {
        "temperature": num("temperature"),
        "pressure": num("pressure"),
        "wind_speed": None,
        "wind_direction": direction if direction in KNOWN_DIRECTIONS else "",
        "cloudiness": int(cur["cloudcover"]) if cur.get("cloudcover") is not None else None,
        "precipitation_amount": num("precip"),
        # описание пригодится для подсказки пользователю
        "description": (cur.get("weather_descriptions") or [""])[0],
        "observation_time": cur.get("observation_time", ""),
        "source": "Weatherstack",
    }
    # Weatherstack отдаёт скорость ветра в км/ч, в наблюдении — м/с
    kmh = num("wind_speed")
    if kmh is not None:
        data["wind_speed"] = round(kmh / 3.6, 1)
    return data


# --- Резервный источник: OpenWeatherMap ------------------------------------
# Если Weatherstack недоступен (сеть, лимит, неактивный ключ), пробуем OWM —
# он уже используется на карте для слоя осадков, ключ лежит в OWM_API_KEY.

def _owm_fetch(latitude, longitude):
    """Текущая погода через OpenWeatherMap. Формат ответа приводим к тому же
    словарю, что и Weatherstack, чтобы вызывающий код не различал источник."""
    if not settings.OWM_API_KEY:
        raise WeatherstackError("Резервный ключ OpenWeatherMap не задан.")
    url = "https://api.openweathermap.org/data/2.5/weather?" + urllib.parse.urlencode({
        "lat": f"{float(latitude):.4f}", "lon": f"{float(longitude):.4f}",
        "appid": settings.OWM_API_KEY, "units": "metric", "lang": "ru"})
    try:
        with urllib.request.urlopen(url, timeout=settings.WEATHERSTACK_TIMEOUT) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        log.warning("OWM HTTP %s", e.code)
        raise WeatherstackError(f"Резервный сервис ответил ошибкой {e.code}.")
    except (urllib.error.URLError, TimeoutError):
        raise WeatherstackError("Резервный сервис погоды недоступен.")
    except (ValueError, json.JSONDecodeError):
        raise WeatherstackError("Резервный сервис вернул неожиданный ответ.")
    return _owm_parse(payload)


# 16 румбов по градусам направления ветра OWM (meteorological, откуда дует)
_OWM_DIRS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
             "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]


def _owm_parse(payload):
    main = (payload or {}).get("main") or {}
    wind = (payload or {}).get("wind") or {}
    clouds = (payload or {}).get("clouds") or {}
    weather = (payload or {}).get("weather") or [{}]
    if not main:
        raise WeatherstackError("В ответе резервного сервиса нет данных.")

    deg = wind.get("deg")
    direction = _OWM_DIRS[round(deg / 22.5) % 16] if deg is not None else ""
    # осадки за последний час, если сервис их вернул
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
        "observation_time": "",
        "source": "OpenWeatherMap",
    }


def fetch_current_with_fallback(latitude, longitude):
    """Сначала Weatherstack, при его отказе — OpenWeatherMap.

    Возвращает тот же словарь полей плюс ключ "source" с именем источника.
    Бросает WeatherstackError только если ОБА сервиса недоступны.
    """
    try:
        data = fetch_current(latitude, longitude)
        data.setdefault("source", "Weatherstack")
        return data
    except WeatherstackError as primary_err:
        log.info("Weatherstack не сработал (%s), пробуем OpenWeatherMap", primary_err)
        try:
            return _owm_fetch(latitude, longitude)
        except WeatherstackError as backup_err:
            # оба источника недоступны — сообщаем об этом одним понятным текстом
            raise WeatherstackError(
                "Не удалось получить погоду ни из одного сервиса. "
                f"Weatherstack: {primary_err} Резерв: {backup_err}")

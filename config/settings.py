"""
Настройки ИС «Дневник синоптика» (ТЗ, раздел 4.7.3).
По умолчанию — SQLite для быстрого запуска в учебной среде.
Для продакшена: PostgreSQL 15+ с PostGIS (см. блок DATABASES ниже).
"""
from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-insecure-key-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "rest_framework",
    "rest_framework.authtoken",
    "drf_spectacular",
    "drf_spectacular_sidecar",   # статика Swagger UI локально
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.vk",
    "accounts",
    "stations",
    "observations",
    "reports",
    "core",
]

# Referrer-Policy: браузер должен отправлять origin на тайл-серверы карт,
# иначе OpenStreetMap отвечает 403 «Referer is required» (политика same-origin,
# которую Django ставит по умолчанию, полностью убирает Referer с чужих доменов).
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "core.middleware.LastActivityMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.debug",
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "core.context_processors.unread_notifications",
        "core.context_processors.vk_auth",
    ]},
}]

WSGI_APPLICATION = "config.wsgi.application"

# --- База данных -----------------------------------------------------------
# Учебный запуск: SQLite (координаты хранятся Decimal, гео-проверки — хаверсин).
# Продакшен по ТЗ: PostgreSQL + PostGIS. Установите переменные окружения
# POSTGRES_DB/USER/PASSWORD/HOST и USE_POSTGRES=1.
if os.environ.get("USE_POSTGRES") == "1":
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "sinoptik"),
        "USER": os.environ.get("POSTGRES_USER", "sinoptik"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }}
else:
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }}

AUTH_USER_MODEL = "accounts.User"
SITE_ID = 1

# --- Вход через сторонние сервисы (VK ID) ----------------------------------
# Кнопка появляется, если заданы учётные данные приложения VK ID
# (https://id.vk.com -> кабинет разработчика). Без них обычная регистрация
# по логину/паролю работает как раньше.
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]
VK_CLIENT_ID = os.environ.get("VK_CLIENT_ID", "")
VK_SECRET = os.environ.get("VK_SECRET", "")
VK_AUTH_ENABLED = bool(VK_CLIENT_ID and VK_SECRET)
SOCIALACCOUNT_PROVIDERS = {
    "vk": {"APP": {"client_id": VK_CLIENT_ID, "secret": VK_SECRET}},
} if VK_AUTH_ENABLED else {}
ACCOUNT_EMAIL_VERIFICATION = "none"
ACCOUNT_LOGIN_METHODS = {"username"}
SOCIALACCOUNT_LOGIN_ON_GET = True     # кнопка ведёт сразу к провайдеру
SOCIALACCOUNT_ADAPTER = "accounts.adapters.SinoptikSocialAdapter"
LOGIN_REDIRECT_URL = "map"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 8}},  # политика пароля ТЗ FR-001
]
# Хэширование паролей: Argon2/PBKDF2 (ТЗ 4.4). PBKDF2 — по умолчанию в Django.

LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "Europe/Moscow"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "map"
LOGOUT_REDIRECT_URL = "map"

# Сессии (ТЗ 4.4): срок 24 ч; выход по неактивности 2 ч — middleware
SESSION_COOKIE_AGE = 24 * 3600
SESSION_IDLE_TIMEOUT = 2 * 3600

# Защита от перебора (ТЗ FR-002): 5 попыток / блокировка 15 минут
LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 15 * 60

# --- Продакшен-безопасность (django check --deploy, OWASP) ------------------
if not DEBUG:
    SECURE_SSL_REDIRECT = os.environ.get("SECURE_SSL_REDIRECT", "1") == "1"
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")  # за Nginx
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30      # 30 дней, затем увеличить
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_CONTENT_TYPE_NOSNIFF = True

# --- Внешний слой осадков на карте (OpenWeatherMap) ------------------------
# Вставьте сюда свой API-ключ с https://home.openweathermap.org/api_keys —
# на карте появится переключаемый слой осадков (дождь и снег) по всей России.
# Пустая строка = слой не подключается, карта работает как обычно.
OWM_API_KEY = os.environ.get("OWM_API_KEY", "")

# --- Подстановка текущей погоды в форму наблюдения (OpenWeatherMap) --------
# Кнопка «Подставить текущую погоду» берёт данные по координатам точки из
# OpenWeatherMap — тем же ключом OWM_API_KEY, что и слой осадков на карте.
# Пустой ключ = кнопка просто не показывается.
WEATHER_TIMEOUT = 6              # секунд: не заставляем пользователя ждать

# --- Реквизиты оператора для страницы политики обработки ПДн (152-ФЗ) ------
# Заполните перед публикацией: эти значения выводятся на /privacy/.
PDN_OPERATOR_NAME = os.environ.get("PDN_OPERATOR_NAME", "оператор Сервиса")
PDN_OPERATOR_CONTACT = os.environ.get("PDN_OPERATOR_CONTACT", "укажите e-mail для обращений")
PDN_POLICY_UPDATED = os.environ.get("PDN_POLICY_UPDATED", "2026 год")

# --- Логирование (ТЗ 4.3: данные для мониторинга и разбора отказов) ---------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"std": {"format": "{asctime} {levelname} {name} {message}",
                            "style": "{"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "std"}},
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
    "loggers": {
        "django.request": {"level": "WARNING"},   # 4xx/5xx с трассировкой
        "django.security": {"level": "WARNING"},
    },
}

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"  # для разработки
DEFAULT_FROM_EMAIL = "noreply@sinoptik.local"
PASSWORD_RESET_TIMEOUT = 24 * 3600  # срок ссылки сброса — 24 ч (ТЗ FR-003)

REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,  # ТЗ FR-007: пагинация 20 записей
    # Точка входа API (приём данных): сессия для браузера, токен для внешних
    # клиентов (мобильные приложения, автоматические станции)
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.TokenAuthentication",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # Троттлинг точки входа (защита от спама скриптами)
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/min",
        "user": "120/min",
        "ingest": "30/min",   # приём наблюдений — отдельный, более строгий лимит
    },
}
SPECTACULAR_SETTINGS = {
    "TITLE": "Дневник синоптика — API",
    "DESCRIPTION": "Точка входа для приёма метеонаблюдений и чтения "
                   "подтверждённых данных (ТЗ 4.7.3, drf-spectacular).",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    # раздаём Swagger UI со своего сервера: не зависим от доступности
    # внешнего CDN (в некоторых сетях он заблокирован)
    "SWAGGER_UI_DIST": "SIDECAR",
    "SWAGGER_UI_FAVICON_HREF": "SIDECAR",
    "REDOC_DIST": "SIDECAR",
}

# --- Celery (ТЗ 4.7.3): фоновая генерация отчётов, письма, периодика -------
# Учебный режим (CELERY_EAGER=1, по умолчанию): задачи выполняются синхронно,
# брокер не требуется. Продакшен: CELERY_EAGER=0 + Redis (ТЗ 4.7.3).
CELERY_TASK_ALWAYS_EAGER = os.environ.get("CELERY_EAGER", "1") == "1"
# Расписание периодических задач (celery beat); в eager-режиме на демо
# задачи можно вызвать вручную: python manage.py shell -c
# "from observations.tasks import cleanup_anonymous_observations as t; t()"
CELERY_BEAT_SCHEDULE = {
    "cleanup-anonymous-observations": {
        "task": "observations.tasks.cleanup_anonymous_observations",
        "schedule": 60 * 60 * 24,        # ежедневно: анонимные старше 30 дней
    },
}

CELERY_BROKER_URL = ("memory://" if CELERY_TASK_ALWAYS_EAGER
                     else os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0"))

# --- Предметные константы (ТЗ 4.6/4.7.1) ------------------------------------
# Допустимые координаты точек наблюдения: территория России с запасом
# (Калининград — Чукотка за 180-м меридианом, Дагестан — Земля Франца-Иосифа).
# Проверка отсеивает опечатки; точные границы в продакшене — полигон в PostGIS.
RUSSIA_BBOX = {"lat_min": 41.0, "lat_max": 82.0, "lon_min": 19.0, "lon_max": 190.0}
STATION_MIN_DISTANCE_M = 10          # FR-004: запрет дублей ближе 10 м
OBSERVATION_MAX_RESUBMITS = 3        # FR-010: не более 3 повторных отправок
PHOTO_MAX_COUNT = 3                  # FR-005
PHOTO_MAX_SIZE = 5 * 1024 * 1024     # 5 МБ
REPORT_MAX_PERIOD_DAYS = 366         # FR-008: период не более 1 года
REPORT_TTL_DAYS = 7                  # хранение готовых отчётов
ANOMALY = {                          # FR-005: критерии аномалий
    "temp_delta": 15.0, "pressure_delta": 30.0,
    "wind_max": 40.0, "precip_max": 100.0,
    "neighbor_radius_km": 50, "neighbor_hours": 3,
    # временная согласованность (практика QC краудсорсинговых метеосетей):
    # скачок температуры к предыдущему замеру той же точки
    "temp_jump": 10.0, "jump_hours": 6,
}
OBSERVATION_ARCHIVE_DAYS = 365       # FR-010: архивация rework/rejected через 12 мес

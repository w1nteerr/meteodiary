# ИС «Дневник синоптика»

Веб-приложение для сбора любительских метеонаблюдений (по РФ): присутствуют точки наблюдения, замеры с офлайн-черновиками, модерация, карта, отчёты.

## Быстрый запуск (учебный режим, SQLite, без Redis)
```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py seed          # справочники + демо-данные
python manage.py runserver
```
Пользователи: `admin`, `moderator`, `observer` — пароль `sinoptik123`.
- Карта: http://127.0.0.1:8000/  Модерация: /moderation/  Админ-панель: /admin/
- API: приём данных POST /api/v1/observations/, документация /api/docs/ (Swagger)
- Письма в dev выводятся в консоль; Celery-задачи выполняются синхронно (EAGER).

## Продакшен (ТЗ 4.7.3/4.7.4)
```bash
export USE_POSTGRES=1 POSTGRES_DB=... POSTGRES_USER=... POSTGRES_PASSWORD=...
export CELERY_EAGER=0 CELERY_BROKER_URL=redis://localhost:6379/0
export DJANGO_DEBUG=0 DJANGO_SECRET_KEY=...
python manage.py migrate && python manage.py collectstatic
gunicorn config.wsgi &
celery -A config worker -B &   # -B: периодические задачи (очистка отчётов)
```
Для точных гео-проверок по границам региона подключите PostGIS
(ENGINE `django.contrib.gis.db.backends.postgis`) — точки помечены комментариями
в `stations/forms.py` и `observations/services.py`.

## Точка входа API (v1)
Приём наблюдений от внешних клиентов (мобильные приложения, скрипты станций):
```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/v1/token/ \
  -d "username=observer&password=sinoptik123" | python -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -X POST http://127.0.0.1:8000/api/v1/observations/ \
  -H "Authorization: Token $TOKEN" -H "Content-Type: application/json" \
  -d '{"point_id":1,"client_uuid":"9f1c2b34-5a6d-4e7f-8a90-b1c2d3e4f567",
       "observed_at":"2026-07-06T09:00:00+03:00","temperature":14.5,
       "pressure":1003.0,"wind_speed":3.2,"wind_direction":"NW",
       "cloudiness":80,"precipitation_amount":1.2,
       "precipitation_type":"rain","phenomena":["fog"]}'
```
Формат тела — как пример JSON в ТЗ п. 4.7.1. Отправка идемпотентна по client_uuid
(повтор возвращает 200 и существующую запись). Чтение подтверждённых данных —
GET /api/v1/observations/ и /api/v1/stations/ без авторизации. Персональный токен
выпускается в профиле или через POST /api/v1/token/. Схема: /api/schema/, /api/docs/.

## Вход через VK ID
Реализован через django-allauth. Зарегистрируйте приложение на id.vk.com и задайте:
```bash
export VK_CLIENT_ID=... VK_SECRET=...
```
Кнопка «Войти через VK ID» появится на странице входа (redirect URI:
https://<домен>/auth/vk/login/callback/). Новому пользователю назначается роль
«Наблюдатель», дата согласия фиксируется при первом входе. Без ключей обычная
регистрация работает как раньше.

## Эксплуатация
- Мониторинг: `GET /healthz` — проверка приложения и БД (опрашивать раз в 60 с
  внешним монитором для расчёта MTBF по ТЗ 4.3).
- Резервное копирование: `python manage.py backup` (БД + фото в `backups/`);
  cron-строка для ежедневного запуска с хранением 14 суток — в шапке команды.
- Логи пишутся в stdout (перехватываются systemd/докером), уровень — `LOG_LEVEL`.
- Троттлинг API: анонимы 60/мин, авторизованные 120/мин, приём наблюдений 30/мин.
- `check --deploy` при DEBUG=0 чист (единственное осознанно отложенное
  предупреждение — HSTS preload, включается после обкатки HTTPS).

## Дашборд
После входа доступен «Дашборд» (/dashboard/): карточки показателей (наблюдения
всего и за 30 дней, активные точки, личная статистика со ссылками на доработки),
сводка мин/сред/макс температуры и четыре графика Chart.js — ход температуры
и давления, осадки по дням, наблюдения по дням, распределение статусов
(пончиковая диаграмма). Состав блоков зависит от роли: модератор дополнительно
видит размер очереди и число аномалий в ней, администратор — счётчик
пользователей со ссылкой в админ-панель.

## PWA и графики
- Карта показывает графики хода температуры/давления и осадков по дням (Chart.js).
- У каждой публичной точки есть страница с историей: `/stations/<id>/page/`.
- Приложение устанавливается на главный экран (Web App Manifest); Service Worker
  кэширует оболочку и форму внесения наблюдения — при отсутствии сети форма
  открывается, черновики живут в IndexedDB (drafts.js).

## Структура
- `accounts` — пользователь/роли, регистрация (FR-001), вход с антибрутфорсом (FR-002),
  сброс пароля (FR-003), выход (FR-011), профиль и анонимизация (FR-012)
- `stations` — точки наблюдения (FR-004, FR-014)
- `observations` — замеры и валидация (FR-005), аномалии, модерация (FR-006),
  доработка (FR-010), история (FR-013), карта и API (FR-007)
- `reports` — отчёты CSV/PDF, Celery (FR-008)
- `core` — уведомления, журнал действий, middleware сессий (ТЗ 4.4)
- `static/js/drafts.js` — офлайн-черновики: IndexedDB + client_uuid (идемпотентность)

## Проверка
Каждый тест запускается на чистой БД (`rm db.sqlite3 && python manage.py migrate && python manage.py seed`):
- `python smoke_test.py` — сценарии FR-001…FR-012 (19 проверок);
- `python smoke_test2.py` — страницы, фото, права, лимит доработок, идемпотентность (22 проверки);
- `python smoke_test3.py` — точка входа API: токены, приём/чтение, Swagger, VK ID (15 проверок);
- `python smoke_test5.py` — дашборд: доступ по ролям, карточки, данные графиков (10 проверок).

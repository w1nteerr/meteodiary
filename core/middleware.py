"""Завершение сессии при неактивности более 2 часов (ТЗ 4.4) +
фиксация последней активности пользователя."""
import time
from django.conf import settings
from django.contrib.auth import logout
from django.utils import timezone


class LastActivityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            now = time.time()
            last = request.session.get("last_seen_ts")
            if last and now - last > settings.SESSION_IDLE_TIMEOUT:
                logout(request)
            else:
                request.session["last_seen_ts"] = now
                # обновляем не чаще раза в 5 минут, чтобы не писать в БД на каждый запрос
                la = request.user.last_activity
                if la is None or (timezone.now() - la).total_seconds() > 300:
                    from django.contrib.auth import get_user_model
                    get_user_model().objects.filter(pk=request.user.pk).update(
                        last_activity=timezone.now())
        return self.get_response(request)

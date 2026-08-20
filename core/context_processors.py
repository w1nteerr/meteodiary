def unread_notifications(request):
    if request.user.is_authenticated:
        return {"unread_count": request.user.notifications.filter(is_read=False).count()}
    return {"unread_count": 0}


def vk_auth(request):
    """Флаги доступности соцвхода: кнопка провайдера показывается,
    только если для него заданы ключи в .env."""
    from django.conf import settings
    return {
        "vk_auth_enabled": getattr(settings, "VK_AUTH_ENABLED", False),
        "yandex_auth_enabled": getattr(settings, "YANDEX_AUTH_ENABLED", False),
        "social_auth_enabled": getattr(settings, "VK_AUTH_ENABLED", False)
                               or getattr(settings, "YANDEX_AUTH_ENABLED", False),
    }

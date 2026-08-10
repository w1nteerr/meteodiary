try:
    from .celery import app as celery_app   # noqa
    __all__ = ("celery_app",)
except Exception:   # Celery не установлен — учебный запуск без фоновых задач
    pass

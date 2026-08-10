import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
app = Celery("sinoptik")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# Периодические задачи (ТЗ 4.7.3): очистка отчётов старше 7 суток — ежедневно
app.conf.beat_schedule = {
    "cleanup-old-reports": {"task": "reports.tasks.cleanup_old_reports",
                            "schedule": 24 * 3600},
    "archive-stale-observations": {"task": "observations.tasks.archive_stale_observations",
                                   "schedule": 24 * 3600},
}

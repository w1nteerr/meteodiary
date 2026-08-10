"""Периодические задачи наблюдений (ТЗ FR-010, celery beat)."""
from datetime import timedelta
from celery import shared_task
from django.conf import settings
from django.utils import timezone


@shared_task
def archive_stale_observations():
    """FR-010: наблюдения в статусах «Доработка» и «Отклонено», не менявшиеся
    12 месяцев, архивируются (скрываются из личного кабинета, soft delete)."""
    from .models import Observation, Status
    limit = timezone.now() - timedelta(days=settings.OBSERVATION_ARCHIVE_DAYS)
    n = (Observation.objects
         .filter(status__in=[Status.REWORK, Status.REJECTED],
                 is_archived=False, updated_at__lt=limit)
         .update(is_archived=True))
    return n


@shared_task
def cleanup_anonymous_observations():
    """Анонимные наблюдения хранятся 30 дней с момента внесения, затем
    удаляются: за них никто не отвечает, и без срока хранения они копили бы
    непроверяемые данные. Запускается ежедневно (celery beat)."""
    from datetime import timedelta

    from django.utils import timezone

    from .models import Observation

    cutoff = timezone.now() - timedelta(days=30)
    deleted, _ = (Observation.objects
                  .filter(extra__anonymous_submission=True,
                          created_at__lt=cutoff)
                  .delete())
    return deleted

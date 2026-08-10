"""Резервное копирование (ТЗ 4.3): БД + каталог фотографий.
Запуск: python manage.py backup [--dest backups]
Продакшен-cron (ежедневно, хранение 14 суток — ТЗ 4.3):
  0 2 * * * cd /srv/sinoptik && python manage.py backup && find backups -mtime +14 -delete
"""
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Резервная копия БД и медиафайлов"

    def add_arguments(self, parser):
        parser.add_argument("--dest", default="backups")

    def handle(self, *args, **opts):
        dest = Path(opts["dest"])
        dest.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        db = settings.DATABASES["default"]
        if db["ENGINE"].endswith("postgresql"):
            out = dest / f"db_{stamp}.dump"
            subprocess.run(
                ["pg_dump", "-Fc", "-h", db["HOST"] or "localhost",
                 "-U", db["USER"], "-f", str(out), db["NAME"]],
                check=True, env={"PGPASSWORD": db["PASSWORD"]})
        else:
            out = dest / f"db_{stamp}.sqlite3"
            shutil.copy2(db["NAME"], out)
        media = Path(settings.MEDIA_ROOT)
        if media.exists() and any(media.iterdir()):
            shutil.make_archive(str(dest / f"media_{stamp}"), "gztar", media)
        self.stdout.write(self.style.SUCCESS(f"Копия создана: {out}"))

"""Резервное копирование (ТЗ 4.3): БД + каталог фотографий.
Запуск: python manage.py backup [--dest backups]
Продакшен-cron (ежедневно, хранение 14 суток — ТЗ 4.3):
  0 2 * * * cd /srv/sinoptik && python manage.py backup && find backups -mtime +14 -delete
"""
import os
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
        parser.add_argument("--keep-days", type=int, default=14,
                            help="сколько суток хранить копии (0 — не удалять)")

    def handle(self, *args, **opts):
        dest = Path(opts["dest"])
        dest.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        db = settings.DATABASES["default"]
        if db["ENGINE"].endswith("postgresql"):
            out = dest / f"db_{stamp}.dump"
            # Копируем текущее окружение и лишь добавляем пароль: если передать
            # только PGPASSWORD, потеряется PATH и pg_dump не найдётся.
            env = os.environ.copy()
            env["PGPASSWORD"] = db["PASSWORD"] or ""
            try:
                subprocess.run(
                    ["pg_dump", "-Fc",
                     "-h", db["HOST"] or "localhost",
                     "-p", str(db["PORT"] or 5432),
                     "-U", db["USER"], "-f", str(out), db["NAME"]],
                    check=True, env=env, capture_output=True, text=True)
            except FileNotFoundError:
                self.stderr.write(self.style.ERROR(
                    "pg_dump не найден. Установите клиент: "
                    "sudo apt install postgresql-client"))
                return
            except subprocess.CalledProcessError as e:
                self.stderr.write(self.style.ERROR(
                    f"pg_dump завершился с ошибкой: {e.stderr.strip()}"))
                return
        else:
            out = dest / f"db_{stamp}.sqlite3"
            shutil.copy2(db["NAME"], out)

        media = Path(settings.MEDIA_ROOT)
        if media.exists() and any(media.iterdir()):
            shutil.make_archive(str(dest / f"media_{stamp}"), "gztar", media)

        size = out.stat().st_size / 1024
        self.stdout.write(self.style.SUCCESS(f"Копия создана: {out} ({size:.0f} КБ)"))

        # Удаляем копии старше указанного срока, чтобы диск не заполнялся
        keep = opts["keep_days"]
        if keep > 0:
            border = datetime.now().timestamp() - keep * 86400
            removed = 0
            for old_file in dest.iterdir():
                if old_file.is_file() and old_file.stat().st_mtime < border:
                    old_file.unlink()
                    removed += 1
            if removed:
                self.stdout.write(f"Удалено устаревших копий: {removed}")

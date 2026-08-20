"""Прописывает домен сайта в таблицу django_site.

Домен используется при формировании ссылок в письмах — восстановление пароля,
подтверждение смены e-mail. По умолчанию Django хранит там example.com, и
ссылки в письмах получаются нерабочими.

    python manage.py set_site_domain
    python manage.py set_site_domain --domain meteodiary.ru
"""
from django.conf import settings
from django.contrib.sites.models import Site
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Прописывает домен сайта (для корректных ссылок в письмах)"

    def add_arguments(self, parser):
        parser.add_argument("--domain", default=None,
                            help="домен; по умолчанию SITE_DOMAIN из настроек")
        parser.add_argument("--name", default=None,
                            help="название сайта; по умолчанию SITE_NAME")

    def handle(self, *args, **opts):
        domain = opts["domain"] or settings.SITE_DOMAIN
        name = opts["name"] or settings.SITE_NAME
        site, _ = Site.objects.update_or_create(
            pk=settings.SITE_ID, defaults={"domain": domain, "name": name})
        self.stdout.write(self.style.SUCCESS(
            f"Сайт #{site.pk}: домен «{site.domain}», название «{site.name}»"))

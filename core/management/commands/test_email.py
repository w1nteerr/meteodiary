"""Проверка настроек почты: отправляет тестовое письмо.

Помогает убедиться, что SMTP настроен верно, не дожидаясь реального
восстановления пароля.

    python manage.py test_email ваша_почта@example.ru
"""
from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.mail import send_mail


class Command(BaseCommand):
    help = "Отправляет тестовое письмо для проверки настроек SMTP"

    def add_arguments(self, parser):
        parser.add_argument("to", help="адрес получателя")

    def handle(self, *args, **opts):
        to = opts["to"]
        backend = settings.EMAIL_BACKEND.rsplit(".", 2)[-2]

        self.stdout.write("Текущие настройки:")
        self.stdout.write(f"  режим:       {backend}")
        self.stdout.write(f"  сервер:      {settings.EMAIL_HOST}:{settings.EMAIL_PORT}")
        self.stdout.write(f"  SSL / TLS:   {settings.EMAIL_USE_SSL} / {settings.EMAIL_USE_TLS}")
        self.stdout.write(f"  ящик:        {settings.EMAIL_HOST_USER or '— не задан —'}")
        self.stdout.write(f"  отправитель: {settings.DEFAULT_FROM_EMAIL}")

        if not settings.EMAIL_HOST_USER:
            self.stdout.write(self.style.WARNING(
                "\nEMAIL_HOST_USER не задан: письмо будет напечатано в консоль, "
                "а не отправлено. Заполните почтовые переменные в .env."))

        try:
            sent = send_mail(
                subject="Дневник синоптика: проверка почты",
                message=("Это тестовое письмо.\n\n"
                         "Если вы его получили, отправка настроена верно: "
                         "восстановление пароля и уведомления будут доходить."),
                from_email=None,          # возьмётся DEFAULT_FROM_EMAIL
                recipient_list=[to],
                fail_silently=False,      # ошибки показываем явно
            )
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"\nОшибка отправки: {type(e).__name__}: {e}"))
            self.stderr.write(
                "Проверьте: пароль приложения (не пароль от аккаунта), "
                "разрешён ли SMTP в настройках почтового ящика, "
                "совпадает ли DEFAULT_FROM_EMAIL с ящиком отправителя.")
            return

        if sent:
            self.stdout.write(self.style.SUCCESS(f"\nОтправлено писем: {sent} → {to}"))
        else:
            self.stderr.write(self.style.ERROR("\nПисьмо не отправлено."))

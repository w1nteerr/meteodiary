"""Сущность «Пользователь» (ТЗ 4.7.1) + служебная запись «Анонимный пользователь»."""
from django.contrib.auth.models import AbstractUser
from django.db import models


class Roles(models.TextChoices):
    GUEST = "guest", "Гость"
    OBSERVER = "observer", "Наблюдатель"
    MODERATOR = "moderator", "Модератор"
    ADMIN = "admin", "Администратор"


class User(AbstractUser):
    # Уникальность e-mail на уровне БД (в дополнение к проверке в форме):
    # null=True, потому что у служебной заглушки и анонимизированных аккаунтов
    # почты нет, а несколько NULL в SQL дубликатами не считаются.
    email = models.EmailField("e-mail", unique=True, null=True, blank=True)
    role = models.CharField("роль", max_length=16, choices=Roles.choices, default=Roles.OBSERVER)
    consent_at = models.DateTimeField("дата согласия на обработку ПД", null=True, blank=True)
    is_blocked = models.BooleanField("заблокирован", default=False)
    block_reason = models.CharField("причина блокировки", max_length=255, blank=True)
    is_deleted = models.BooleanField("удалён (анонимизирован)", default=False)
    last_activity = models.DateTimeField("последняя активность", null=True, blank=True)

    ANONYMOUS_USERNAME = "anonymous"

    class Meta:
        verbose_name = "пользователь"
        verbose_name_plural = "пользователи"

    @classmethod
    def get_anonymous_stub(cls):
        """Служебная запись «Анонимный пользователь» (ТЗ 4.4): создаётся при первом обращении,
        вход под ней невозможен (unusable password, is_active=False)."""
        stub, created = cls.objects.get_or_create(
            username=cls.ANONYMOUS_USERNAME,
            defaults={"first_name": "Анонимный", "last_name": "пользователь",
                      "email": None, "is_active": False, "role": Roles.OBSERVER},
        )
        if created:
            stub.set_unusable_password()
            stub.save(update_fields=["password"])
        return stub

    def anonymize(self):
        """Процедура анонимизации (ТЗ 4.4, FR-009/FR-012): затирание ПД, перенос авторства.
        Метки времени, геопривязка и значения наблюдений сохраняются."""
        from observations.models import Observation
        from rest_framework.authtoken.models import Token
        Token.objects.filter(user=self).delete()   # отзыв API-токена
        stub = User.get_anonymous_stub()
        Observation.objects.filter(author=self).update(author=stub)
        self.username = f"deleted_{self.pk}"
        self.email = None   # None, а не "", чтобы не нарушать unique
        self.first_name = self.last_name = ""
        self.set_unusable_password()
        self.is_active = False
        self.is_deleted = True
        self.save()

    @property
    def is_moderator(self):
        return self.role in (Roles.MODERATOR, Roles.ADMIN) or self.is_superuser

    @property
    def is_admin_role(self):
        return self.role == Roles.ADMIN or self.is_superuser

"""Адаптер социального входа (VK ID и Яндекс ID).

Задачи адаптера:
— назначить новому пользователю роль «Наблюдатель»;
— зафиксировать момент первого входа как согласие на обработку данных
  (пользователь подтверждает передачу данных на экране провайдера);
— подставить e-mail и осмысленный логин из данных провайдера, а не оставлять
  автосгенерированный «user123» с пустой почтой;
— не допустить конфликта уникальности e-mail: если такой адрес уже занят,
  привязать вход к существующему аккаунту.
"""
import re
import unicodedata

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.utils import timezone

from .models import Roles, User


def _translit(value):
    """Грубая транслитерация: «Иван Петров» → «ivan-petrov».

    Логин хранится латиницей, чтобы не ломались ссылки и выгрузки.
    """
    table = {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
        "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
        "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
        "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch",
        "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    }
    out = "".join(table.get(ch, ch) for ch in (value or "").lower())
    out = unicodedata.normalize("NFKD", out).encode("ascii", "ignore").decode()
    out = re.sub(r"[^a-z0-9]+", "-", out).strip("-")
    return out[:28]


def _unique_username(base):
    """Подбирает свободный логин: ivan, ivan-2, ivan-3…"""
    base = base or "observer"
    candidate = base
    n = 1
    while User.objects.filter(username__iexact=candidate).exists():
        n += 1
        candidate = f"{base}-{n}"
    return candidate


class SinoptikSocialAdapter(DefaultSocialAccountAdapter):

    def pre_social_login(self, request, sociallogin):
        """Если пользователь с такой почтой уже зарегистрирован обычным
        способом, привязываем соцвход к нему, а не создаём второй аккаунт
        (иначе уникальность e-mail не даст сохранить нового)."""
        if sociallogin.is_existing:
            return
        email = (sociallogin.account.extra_data or {}).get("default_email") \
            or (sociallogin.user.email or "")
        email = email.strip().lower()
        if not email:
            return
        existing = User.objects.filter(email__iexact=email).first()
        if existing:
            sociallogin.connect(request, existing)

    def populate_user(self, request, sociallogin, data):
        """Заполняет поля нового пользователя данными провайдера."""
        user = super().populate_user(request, sociallogin, data)
        extra = sociallogin.account.extra_data or {}

        # почта: у Яндекса это default_email, у VK может прийти в data
        email = (data.get("email") or extra.get("default_email")
                 or extra.get("email") or "").strip().lower()
        user.email = email or None      # None, а не "", из-за unique=True

        # имя и фамилия
        first = data.get("first_name") or extra.get("first_name") or ""
        last = data.get("last_name") or extra.get("last_name") or ""
        if not first and extra.get("real_name"):
            parts = str(extra["real_name"]).split()
            first = parts[0] if parts else ""
            last = " ".join(parts[1:])
        user.first_name, user.last_name = first, last

        # логин: из почты, имени или логина провайдера — но не «user123»
        base = ""
        if email:
            base = _translit(email.split("@")[0])
        if not base:
            base = _translit(f"{first} {last}".strip())
        if not base:
            base = _translit(extra.get("login") or data.get("username") or "")
        user.username = _unique_username(base or "observer")
        return user

    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)
        user.role = Roles.OBSERVER
        # вход через провайдера = подтверждение передачи данных
        user.consent_at = timezone.now()
        user.save(update_fields=["role", "consent_at"])
        return user

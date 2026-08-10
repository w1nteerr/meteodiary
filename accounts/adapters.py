"""Адаптер социального входа (VK ID): новому пользователю назначается роль
«Наблюдатель», момент первого входа фиксируется как согласие на обработку ПД
(пользователь подтверждает передачу данных на экране провайдера)."""
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.utils import timezone

from .models import Roles


class SinoptikSocialAdapter(DefaultSocialAccountAdapter):
    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)
        user.role = Roles.OBSERVER
        user.consent_at = timezone.now()
        user.save(update_fields=["role", "consent_at"])
        return user

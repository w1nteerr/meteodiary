"""FR-001 регистрация, FR-002 вход (антибрутфорс), FR-003 сброс пароля,
FR-011 выход, FR-012 профиль/удаление аккаунта."""
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.core.cache import cache
from django.shortcuts import render, redirect
from django.utils import timezone

from django.core import signing
from django.core.mail import send_mail
from rest_framework.authtoken.models import Token

from core.services import audit

log = logging.getLogger(__name__)
from .forms import RegisterForm, MathCaptchaMixin, EmailChangeForm, DeleteAccountForm
from .models import Roles


def _send_welcome_email(request, user):
    """Приветственное письмо после регистрации.

    Отправка не должна мешать регистрации: при недоступном SMTP пользователь
    всё равно попадает в аккаунт, а ошибка уходит в лог.
    """
    if not user.email:
        return
    try:
        send_mail(
            "Добро пожаловать в «Дневник синоптика»",
            (f"Здравствуйте, {user.username}!\n\n"
             "Вы зарегистрировались в сервисе «Дневник синоптика».\n\n"
             "Что можно делать:\n"
             "• создать свои точки наблюдения;\n"
             "• вносить замеры — полные, экспресс или аллергонаблюдения;\n"
             "• смотреть карту, графики и формировать отчёты.\n\n"
             "Внесённые наблюдения проходят проверку модератором, после чего\n"
             "появляются на общей карте.\n\n"
             f"Сайт: https://{settings.SITE_DOMAIN}/\n\n"
             "Если вы не регистрировались, просто проигнорируйте это письмо."),
            None, [user.email], fail_silently=True)
    except Exception:
        log.warning("Не удалось отправить приветственное письмо", exc_info=True)


def register(request):
    """FR-001: регистрация наблюдателя (CAPTCHA, согласие на ПД, авто-вход)."""
    if request.method == "POST":
        form = RegisterForm(request.POST, session=request.session)
        if form.is_valid():
            user = form.save(commit=False)
            user.role = Roles.OBSERVER
            user.consent_at = timezone.now()   # фиксация согласия (ТЗ 4.4)
            user.save()
            audit(request, "register", obj=f"user:{user.pk}")
            _send_welcome_email(request, user)
            # при нескольких бэкендах (пароль + VK ID) бэкенд указывается явно
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            messages.success(request, "Регистрация выполнена. Добро пожаловать!")
            return redirect("map")
    else:
        form = RegisterForm(session=request.session)
    challenge = MathCaptchaMixin.make_challenge(request.session)
    return render(request, "accounts/register.html", {"form": form, "captcha_q": challenge})


def _lock_key(request, username):
    ip = request.META.get("REMOTE_ADDR", "?")
    return f"login-fail:{username}:{ip}"


def login_view(request):
    """FR-002: вход. Лимит 5 неудачных попыток на пару логин+IP, блокировка 15 мин."""
    error = None
    if request.method == "POST":
        username = request.POST.get("username", "")
        key = _lock_key(request, username)
        fails = cache.get(key, 0)
        if fails >= settings.LOGIN_MAX_ATTEMPTS:
            error = "Слишком много неудачных попыток. Вход заблокирован на 15 минут."
            audit(request, "login_locked", obj=f"username:{username}")
        else:
            form = AuthenticationForm(request, data=request.POST)
            if form.is_valid():
                user = form.get_user()
                if getattr(user, "is_blocked", False):
                    error = "Учётная запись заблокирована. Обратитесь к администратору."
                else:
                    cache.delete(key)
                    login(request, user)
                    audit(request, "login", obj=f"user:{user.pk}")
                    return redirect(request.GET.get("next") or "map")
            else:
                cache.set(key, fails + 1, settings.LOGIN_LOCKOUT_SECONDS)
                audit(request, "login_fail", obj=f"username:{username}")
                error = "Неверный логин или пароль."   # без раскрытия деталей (ТЗ FR-002)
    return render(request, "accounts/login.html", {"error": error})


@login_required
def logout_view(request):
    """FR-011: выход — инвалидация сессии на сервере."""
    audit(request, "logout", obj=f"user:{request.user.pk}")
    logout(request)
    messages.info(request, "Вы вышли из системы.")
    return redirect("map")


@login_required
def profile(request):
    """FR-012: смена e-mail, пароля, удаление аккаунта."""
    email_form = EmailChangeForm(prefix="em")
    pwd_form = PasswordChangeForm(user=request.user, prefix="pw")
    del_form = DeleteAccountForm(user=request.user, prefix="dl")

    if request.method == "POST":
        if "change_email" in request.POST:
            email_form = EmailChangeForm(request.POST, prefix="em")
            if email_form.is_valid():
                # ТЗ FR-012: изменение вступает в силу после перехода по ссылке,
                # отправленной на НОВЫЙ адрес (срок действия 24 часа)
                new_email = email_form.cleaned_data["new_email"]
                token = signing.dumps({"uid": request.user.pk, "email": new_email},
                                      salt="email-change")
                link = request.build_absolute_uri(f"/accounts/confirm-email/{token}/")
                send_mail("Подтверждение смены e-mail",
                          f"Для подтверждения нового адреса перейдите по ссылке "
                          f"(действует 24 часа): {link}", None, [new_email],
                          fail_silently=True)
                audit(request, "email_change_request", obj=f"user:{request.user.pk}",
                      new=new_email)
                messages.info(request, "Ссылка подтверждения отправлена на новый адрес. "
                                       "E-mail изменится после перехода по ней.")
                return redirect("profile")
        elif "change_password" in request.POST:
            pwd_form = PasswordChangeForm(user=request.user, data=request.POST, prefix="pw")
            if pwd_form.is_valid():
                pwd_form.save()
                update_session_auth_hash(request, request.user)  # прочие сессии завершатся
                audit(request, "password_change", obj=f"user:{request.user.pk}")
                messages.success(request, "Пароль изменён.")
                return redirect("profile")
        elif "api_token" in request.POST:
            # Точка входа API: перевыпуск персонального токена
            Token.objects.filter(user=request.user).delete()
            token = Token.objects.create(user=request.user)
            audit(request, "api_token_issue", obj=f"user:{request.user.pk}")
            messages.success(request, f"Новый API-токен: {token.key} — сохраните его, "
                                      "он показывается один раз.")
            return redirect("profile")
        elif "delete_account" in request.POST:
            del_form = DeleteAccountForm(request.POST, user=request.user, prefix="dl")
            if del_form.is_valid():
                audit(request, "account_delete", obj=f"user:{request.user.pk}")
                user = request.user
                logout(request)
                user.anonymize()
                messages.info(request, "Аккаунт удалён, данные анонимизированы.")
                return redirect("map")
    has_token = Token.objects.filter(user=request.user).exists()
    return render(request, "accounts/profile.html",
                  {"email_form": email_form, "pwd_form": pwd_form,
                   "del_form": del_form, "has_token": has_token})


def confirm_email(request, token):
    """FR-012: применение смены e-mail по подписанной ссылке (24 часа)."""
    from accounts.models import User
    try:
        data = signing.loads(token, salt="email-change", max_age=24 * 3600)
    except signing.BadSignature:
        messages.error(request, "Ссылка подтверждения недействительна или устарела.")
        return redirect("map")
    user = User.objects.filter(pk=data["uid"]).first()
    if not user or User.objects.filter(email__iexact=data["email"]).exclude(pk=user.pk).exists():
        messages.error(request, "Не удалось применить смену e-mail.")
        return redirect("map")
    old = user.email
    user.email = data["email"]
    user.save(update_fields=["email"])
    audit(request, "email_change_confirm", obj=f"user:{user.pk}", old=old, new=user.email)
    messages.success(request, "E-mail подтверждён и обновлён.")
    return redirect("profile" if request.user.is_authenticated else "login")

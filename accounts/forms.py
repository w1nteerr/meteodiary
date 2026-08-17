"""Формы FR-001 (регистрация с CAPTCHA и согласием), FR-012 (профиль)."""
import random
from django import forms
from django.utils.safestring import mark_safe
from django.contrib.auth.forms import UserCreationForm
from .models import User


class MathCaptchaMixin(forms.Form):
    """Встроенная текстовая CAPTCHA (арифметика) — резервный вариант по ТЗ FR-001.
    Внешний сервис (reCAPTCHA) подключается в продакшене; при его недоступности
    используется эта проверка, регистрация без CAPTCHA невозможна."""
    captcha = forms.IntegerField(label="Проверка: решите пример")

    @staticmethod
    def make_challenge(session):
        a, b = random.randint(1, 9), random.randint(1, 9)
        session["captcha_answer"] = a + b
        return f"{a} + {b} = ?"

    def clean_captcha(self):
        val = self.cleaned_data["captcha"]
        expected = self.session.pop("captcha_answer", None)
        if expected is None or val != expected:
            raise forms.ValidationError("Неверный ответ на проверку. Попробуйте ещё раз.")
        return val


class RegisterForm(MathCaptchaMixin, UserCreationForm):
    email = forms.EmailField(label="E-mail", required=True)
    # ссылка на политику обязательна: согласие должно быть информированным
    consent = forms.BooleanField(required=True, label=mark_safe(
        'Согласен с условиями '
        '<a href="/privacy/" target="_blank" rel="noopener">обработки данных</a>'))

    class Meta:
        model = User
        fields = ("username", "email")

    def __init__(self, *args, session=None, **kwargs):
        self.session = session
        super().__init__(*args, **kwargs)

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            # в т.ч. заблокированные/удалённые — причина не раскрывается (ТЗ FR-001)
            raise forms.ValidationError("E-mail недоступен.")
        return email

    def clean_username(self):
        username = self.cleaned_data["username"]
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Логин недоступен.")
        return username


class EmailChangeForm(forms.Form):
    new_email = forms.EmailField(label="Новый e-mail")

    def clean_new_email(self):
        email = self.cleaned_data["new_email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("E-mail недоступен.")
        return email


class DeleteAccountForm(forms.Form):
    password = forms.CharField(label="Текущий пароль", widget=forms.PasswordInput)
    confirm = forms.BooleanField(label="Понимаю, что удаление необратимо; наблюдения будут анонимизированы")

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_password(self):
        if not self.user.check_password(self.cleaned_data["password"]):
            raise forms.ValidationError("Неверный пароль.")
        return self.cleaned_data["password"]

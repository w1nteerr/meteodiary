"""FR-005: форма наблюдения с валидацией диапазонов и фото."""
from django import forms
from django.conf import settings
from .models import Allergen, Observation, ObsType, Phenomenon

# Категории для быстрых форм: пользователь выбирает словами, а в БД
# сохраняется представительное числовое значение — графики, роза ветров
# и отчёты продолжают работать со своими числами.
WIND_LEVELS = [("weak", "Слабый (до 3 м/с)"),
               ("moderate", "Умеренный (4–7 м/с)"),
               ("strong", "Сильный (8 м/с и больше)")]
WIND_VALUES = {"weak": 2, "moderate": 5, "strong": 12}

CLOUD_LEVELS = [("clear", "Ясно"),
                ("partly", "Переменная облачность"),
                ("overcast", "Пасмурно")]
CLOUD_VALUES = {"clear": 10, "partly": 50, "overcast": 90}


class QuickFieldsMixin:
    """Добавляет к форме поля-категории «Ветер» и «Облачность» и переносит
    выбранное в числовые wind_speed / cloudiness при сохранении."""

    def add_quick_fields(self):
        self.fields["wind_level"] = forms.ChoiceField(
            choices=[("", "—")] + WIND_LEVELS, required=False, label="Ветер")
        self.fields["cloud_level"] = forms.ChoiceField(
            choices=[("", "—")] + CLOUD_LEVELS, required=False, label="Облачность")
        # при доработке ранее сохранённого замера подставляем ближайшую категорию
        inst = getattr(self, "instance", None)
        if inst and inst.pk:
            if inst.wind_speed is not None:
                w = float(inst.wind_speed)
                self.fields["wind_level"].initial = (
                    "weak" if w <= 3 else "moderate" if w <= 7 else "strong")
            if inst.cloudiness is not None:
                c = inst.cloudiness
                self.fields["cloud_level"].initial = (
                    "clear" if c <= 20 else "partly" if c <= 70 else "overcast")

    def apply_quick_fields(self, data, obs_type):
        """Категории → числа. Вызывается из clean() до проверки обязательности."""
        if obs_type != ObsType.FULL:
            wl = data.get("wind_level")
            cl = data.get("cloud_level")
            if wl:
                data["wind_speed"] = WIND_VALUES[wl]
            if cl:
                data["cloudiness"] = CLOUD_VALUES[cl]
        return data


class ObservationForm(QuickFieldsMixin, forms.ModelForm):
    phenomena = forms.ModelMultipleChoiceField(
        queryset=Phenomenon.objects.filter(is_active=True), required=False,
        widget=forms.CheckboxSelectMultiple, label="Погодные явления")

    class Meta:
        model = Observation
        fields = ["obs_type", "station", "observed_at", "temperature", "pressure",
                  "wind_speed", "wind_direction", "precipitation_amount",
                  "precipitation_type", "cloudiness", "water_temperature",
                  "phenomena", "pollen_level", "allergen"]
        widgets = {"observed_at": forms.DateTimeInput(attrs={"type": "datetime-local"})}

    # Обязательные поля каждого типа (сверх температуры, точки и времени).
    # Остальные поля типа — по желанию; поля чужих типов скрываются в форме
    # и очищаются в clean().
    REQUIRED_BY_TYPE = {
        # полное — всё как в ТЗ; экспресс — только температура;
        # аллерго — только уровень пыльцы (температура не нужна вовсе)
        ObsType.FULL: ["temperature", "pressure", "wind_speed", "cloudiness",
                       "precipitation_type"],
        ObsType.EXPRESS: ["temperature"],
        ObsType.ALLERGY: ["pollen_level"],
    }
    # Поля, относящиеся ТОЛЬКО к перечисленным типам.
    # Давление и румб — только для полного наблюдения: в экспресс-замере
    # их незачем спрашивать.
    TYPE_ONLY_FIELDS = {
        "pollen_level": {ObsType.ALLERGY}, "allergen": {ObsType.ALLERGY},
        "precipitation_amount": {ObsType.FULL},
        "precipitation_type": {ObsType.FULL},
        "pressure": {ObsType.FULL},
        "wind_direction": {ObsType.FULL},
        "cloudiness": {ObsType.FULL, ObsType.EXPRESS},
        "temperature": {ObsType.FULL, ObsType.EXPRESS},
        "water_temperature": {ObsType.FULL},
        "phenomena": {ObsType.FULL},
    }

    def clean(self):
        data = super().clean()
        t = data.get("obs_type") or ObsType.FULL
        data = self.apply_quick_fields(data, t)
        for f in self.REQUIRED_BY_TYPE.get(t, []):
            if data.get(f) in (None, "", []):
                self.add_error(f, "Обязательное поле для этого типа наблюдения.")
        # значения полей чужих типов не сохраняем, даже если пришли в POST
        # Текстовые поля (pollen_level, wind_direction) объявлены как
        # CharField(blank=True) без null — их очищаем пустой строкой, иначе
        # None нарушает NOT NULL и сохранение падает с IntegrityError.
        BLANK_STR = {"pollen_level", "wind_direction"}
        for f, types in self.TYPE_ONLY_FIELDS.items():
            if t not in types and f in data:
                data[f] = "" if f in BLANK_STR else None
                if f == "precipitation_amount":
                    data[f] = 0
                if f == "phenomena":
                    data[f] = Phenomenon.objects.none()
        return data

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        # по типам поля не обязательны на уровне HTML — обязательность
        # проверяет clean() в зависимости от выбранного типа
        for f in ("temperature", "pressure", "wind_speed", "cloudiness",
                  "precipitation_type", "precipitation_amount",
                  "pollen_level", "allergen"):
            self.fields[f].required = False
        self.fields["allergen"].queryset = Allergen.objects.filter(is_active=True)
        self.add_quick_fields()
        if user is not None:
            # FR-004/FR-005: замер вносится только с активной точки владельца.
            # При доработке (FR-010) текущая точка остаётся допустимой,
            # даже если она была архивирована после создания наблюдения.
            qs = user.stations.filter(is_active=True)
            if self.instance.pk and self.instance.station_id:
                from stations.models import Station
                qs = qs | Station.objects.filter(pk=self.instance.station_id)
            self.fields["station"].queryset = qs.distinct()
        self.fields["precipitation_type"].queryset = \
            self.fields["precipitation_type"].queryset.filter(is_active=True)


def validate_photos(files):
    """FR-005: не более 3 фото, JPEG/PNG, каждое ≤ 5 МБ."""
    if len(files) > settings.PHOTO_MAX_COUNT:
        raise forms.ValidationError(f"Не более {settings.PHOTO_MAX_COUNT} фотографий.")
    for f in files:
        if f.size > settings.PHOTO_MAX_SIZE:
            raise forms.ValidationError(f"Файл «{f.name}» больше 5 МБ.")
        if f.content_type not in ("image/jpeg", "image/png"):
            raise forms.ValidationError(f"Файл «{f.name}»: допустимы только JPEG и PNG.")


class AnonymousObservationForm(QuickFieldsMixin, forms.ModelForm):
    """Анонимное наблюдение без регистрации: наблюдатель вводит только
    координаты (широту и долготу) и, по желанию, название места — привязка
    к точке создаётся автоматически. Фото недоступны. Скрытое поле-«приманка»
    отсеивает простых спам-ботов."""
    website = forms.CharField(required=False, widget=forms.HiddenInput)  # honeypot
    # координаты вместо выбора точки из списка
    latitude = forms.DecimalField(
        label="Широта", min_value=-90, max_value=90, max_digits=9, decimal_places=6,
        widget=forms.NumberInput(attrs={"step": "any", "placeholder": "например, 55.751244"}))
    longitude = forms.DecimalField(
        label="Долгота", min_value=-180, max_value=180, max_digits=9, decimal_places=6,
        widget=forms.NumberInput(attrs={"step": "any", "placeholder": "например, 37.618423"}))
    place_name = forms.CharField(
        label="Название места (необязательно)", required=False, max_length=120,
        widget=forms.TextInput(attrs={"placeholder": "например, Москва, парк"}))

    class Meta:
        model = Observation
        # station убран из формы — точка определяется по координатам в save()
        fields = ["obs_type", "observed_at", "temperature", "pressure",
                  "wind_speed", "wind_direction", "precipitation_amount",
                  "precipitation_type", "cloudiness", "pollen_level", "allergen"]
        widgets = {"observed_at": forms.DateTimeInput(attrs={"type": "datetime-local"})}

    # анонимно доступны те же типы; правила обязательности — общие с основной
    # формой (см. ObservationForm), фото и явления анонимам недоступны
    REQUIRED_BY_TYPE = {
        ObsType.FULL: ["temperature", "pressure", "wind_speed", "cloudiness",
                       "precipitation_type"],
        ObsType.EXPRESS: ["temperature"],
        ObsType.ALLERGY: ["pollen_level"],
    }
    TYPE_ONLY_FIELDS = {
        "pollen_level": {ObsType.ALLERGY}, "allergen": {ObsType.ALLERGY},
        "precipitation_amount": {ObsType.FULL}, "precipitation_type": {ObsType.FULL},
        "pressure": {ObsType.FULL},
        "wind_direction": {ObsType.FULL},
        "cloudiness": {ObsType.FULL, ObsType.EXPRESS},
        "temperature": {ObsType.FULL, ObsType.EXPRESS},
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in ("temperature", "pressure", "wind_speed", "cloudiness",
                  "precipitation_type", "precipitation_amount",
                  "pollen_level", "allergen"):
            self.fields[f].required = False
        self.fields["allergen"].queryset = Allergen.objects.filter(is_active=True)
        self.add_quick_fields()
        self.fields["precipitation_type"].queryset = \
            self.fields["precipitation_type"].queryset.filter(is_active=True)

    def clean(self):
        data = super().clean()
        if data.get("website"):                     # бот заполнил скрытое поле
            raise forms.ValidationError("Не удалось отправить форму. Попробуйте ещё раз.")
        t = data.get("obs_type") or ObsType.FULL
        data = self.apply_quick_fields(data, t)
        for f in self.REQUIRED_BY_TYPE.get(t, []):
            if data.get(f) in (None, "", []):
                self.add_error(f, "Обязательное поле для этого типа наблюдения.")
        BLANK_STR = {"pollen_level", "wind_direction"}
        for f, types in self.TYPE_ONLY_FIELDS.items():
            if t not in types and f in data:
                data[f] = "" if f in BLANK_STR else None
                if f == "precipitation_amount":
                    data[f] = 0
        return data

    def save(self, commit=True):
        """Находит или создаёт точку по введённым координатам и привязывает к
        ней наблюдение. Все анонимные точки принадлежат служебному
        пользователю и не публикуются в общем списке точек."""
        from accounts.models import User as UserModel
        from stations.models import Station
        obs = super().save(commit=False)
        lat = self.cleaned_data["latitude"]
        lon = self.cleaned_data["longitude"]
        name = (self.cleaned_data.get("place_name") or "").strip()
        stub = UserModel.get_anonymous_stub()
        # координаты округляем до ~11 м, чтобы близкие замеры шли в одну точку
        lat_r = round(float(lat), 4)
        lon_r = round(float(lon), 4)
        station = (Station.objects
                   .filter(owner=stub, latitude=lat_r, longitude=lon_r).first())
        if station is None:
            station = Station.objects.create(
                owner=stub,
                name=name or f"Аноним {lat_r:.4f}, {lon_r:.4f}",
                latitude=lat_r, longitude=lon_r,
                is_public=False,   # анонимные точки не показываем в списке точек
                is_active=True)
        obs.station = station
        if commit:
            obs.save()
            self.save_m2m()
        return obs

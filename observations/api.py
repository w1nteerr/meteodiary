"""Точка входа API (v1): приём метеонаблюдений от внешних клиентов
(мобильные приложения, скрипты автоматических станций) и чтение
подтверждённых данных. Аутентификация — токен (DRF authtoken) или сессия.

POST /api/v1/observations/  — приём наблюдения (идемпотентно по client_uuid)
GET  /api/v1/observations/  — подтверждённые наблюдения публичных точек
GET  /api/v1/stations/      — публичные активные точки
POST /api/v1/token/         — получение API-токена по логину/паролю
"""
from django.db import IntegrityError
from rest_framework import serializers, viewsets, mixins, permissions, status
from rest_framework.response import Response

from core.services import audit
from stations.models import Station
from .models import Observation, Status, PrecipitationType, Phenomenon
from .services import check_anomaly


class StationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Station
        fields = ["id", "name", "latitude", "longitude", "height", "is_public"]


class ObservationReadSerializer(serializers.ModelSerializer):
    station = StationSerializer(read_only=True)
    precipitation_type = serializers.SlugRelatedField(slug_field="code", read_only=True)
    phenomena = serializers.SlugRelatedField(slug_field="code", many=True, read_only=True)

    class Meta:
        model = Observation
        fields = ["id", "station", "observed_at", "temperature", "pressure",
                  "wind_speed", "wind_direction", "precipitation_amount",
                  "precipitation_type", "cloudiness", "phenomena", "status"]


class ObservationWriteSerializer(serializers.ModelSerializer):
    """Входной формат соответствует примеру JSON из ТЗ п. 4.7.1:
    point_id, client_uuid, observed_at, temperature (°C), pressure (гПа),
    wind_speed (м/с), wind_direction (румб), cloudiness (%),
    precipitation_amount (мм), precipitation_type (код), phenomena (коды)."""
    point_id = serializers.PrimaryKeyRelatedField(
        source="station", queryset=Station.objects.filter(is_active=True))
    client_uuid = serializers.UUIDField(required=False)
    precipitation_type = serializers.SlugRelatedField(
        slug_field="code", queryset=PrecipitationType.objects.filter(is_active=True))
    phenomena = serializers.SlugRelatedField(
        slug_field="code", many=True, required=False,
        queryset=Phenomenon.objects.filter(is_active=True))

    class Meta:
        model = Observation
        fields = ["point_id", "client_uuid", "observed_at", "temperature",
                  "pressure", "wind_speed", "wind_direction",
                  "precipitation_amount", "precipitation_type",
                  "cloudiness", "phenomena"]

    def validate_point_id(self, station):
        user = self.context["request"].user
        if station.owner_id != user.pk:
            raise serializers.ValidationError(
                "Наблюдения можно вносить только со своих точек.")
        return station

    def validate(self, data):
        # диапазоны модели (MinValue/MaxValue) DRF проверяет автоматически
        return data


class ObservationViewSet(mixins.CreateModelMixin, mixins.ListModelMixin,
                         mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    throttle_scope = "ingest"   # строгий лимит на приём (30/мин)

    def get_throttles(self):
        from rest_framework.throttling import ScopedRateThrottle, AnonRateThrottle
        if self.action == "create":
            return [ScopedRateThrottle()]
        return [AnonRateThrottle()]

    def get_queryset(self):
        return (Observation.objects
                .filter(status=Status.APPROVED, station__is_public=True,
                        station__is_active=True, is_archived=False)
                .select_related("station", "precipitation_type")
                .prefetch_related("phenomena")
                .order_by("-observed_at"))

    def get_serializer_class(self):
        return (ObservationWriteSerializer if self.action == "create"
                else ObservationReadSerializer)

    def get_permissions(self):
        if self.action == "create":
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]

    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        cu = ser.validated_data.get("client_uuid")
        if cu:
            existing = Observation.objects.filter(client_uuid=cu).first()
            if existing:   # идемпотентность (ТЗ FR-005): дубль не создаётся
                return Response(
                    ObservationReadSerializer(existing).data, status=status.HTTP_200_OK)
        phenomena = ser.validated_data.pop("phenomena", [])
        obs = Observation(author=request.user, status=Status.PENDING,
                          **ser.validated_data)
        obs = check_anomaly(obs)
        try:
            obs.save()
        except IntegrityError:
            existing = Observation.objects.get(client_uuid=obs.client_uuid)
            return Response(ObservationReadSerializer(existing).data,
                            status=status.HTTP_200_OK)
        obs.phenomena.set(phenomena)
        audit(request, "observation_create_api", obj=f"observation:{obs.pk}")
        return Response(ObservationReadSerializer(obs).data,
                        status=status.HTTP_201_CREATED)


class StationViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = StationSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        qs = Station.objects.filter(is_active=True)
        # свои точки видны всегда, чужие — только публичные
        if self.request.user.is_authenticated:
            from django.db.models import Q
            return qs.filter(Q(is_public=True) | Q(owner=self.request.user))
        return qs.filter(is_public=True)

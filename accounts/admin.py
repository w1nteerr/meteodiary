"""FR-009: администрирование пользователей (блокировка с причиной, мягкое удаление)."""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User


@admin.register(User)
class SinoptikUserAdmin(UserAdmin):
    list_display = ("username", "email", "role", "is_blocked", "is_deleted",
                    "last_activity", "consent_at")
    list_filter = ("role", "is_blocked", "is_deleted")
    fieldsets = UserAdmin.fieldsets + (
        ("Дневник синоптика", {"fields": ("role", "consent_at", "is_blocked",
                                          "block_reason", "is_deleted", "last_activity")}),
    )
    actions = ["block_users", "unblock_users", "soft_delete"]

    @admin.action(description="Заблокировать (укажите причину в карточке)")
    def block_users(self, request, queryset):
        queryset.update(is_blocked=True)

    @admin.action(description="Разблокировать")
    def unblock_users(self, request, queryset):
        queryset.update(is_blocked=False, block_reason="")

    @admin.action(description="Мягко удалить (анонимизация, ТЗ 4.4)")
    def soft_delete(self, request, queryset):
        for u in queryset:
            u.anonymize()

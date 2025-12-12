from django.contrib import admin
from .models import StepPaymentAlgorithm, MoneyDeductionLog
from django.contrib.auth.models import User
from .models import FamilyMember

# Удалить закомментированный код и избыточные методы
@admin.register(StepPaymentAlgorithm)
class StepPaymentAlgorithmAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'kilometers', 'amount_earned', 'created_at')
    list_filter = ('created_at', 'user')
    search_fields = ('user__username', 'user__first_name', 'user__last_name')
    readonly_fields = ('created_at',)

    fieldsets = (
        ('Основная информация', {
            'fields': ('user', 'kilometers', 'amount_earned')
        }),
        ('Дополнительная информация', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )


@admin.register(MoneyDeductionLog)
class MoneyDeductionLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'amount', 'deducted_by', 'created_at')
    list_filter = ('created_at', 'user', 'deducted_by')
    search_fields = ('user__username', 'reason', 'deducted_by__username')
    readonly_fields = ('created_at', 'balance_before', 'balance_after', 'deducted_by')  # сделать readonly

    fieldsets = (
        ('Основная информация', {
            'fields': ('user', 'amount', 'reason', 'deducted_by')
        }),
        ('Баланс', {
            'fields': ('balance_before', 'balance_after'),
            'classes': ('collapse',)
        }),
        ('Дополнительная информация', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )

    # Ограничить удаление
    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return False  # если запрещено редактировать


@admin.register(FamilyMember)
class FamilyMemberAdmin(admin.ModelAdmin):
    list_display = ('user', 'relationship', 'birthday', 'is_close_relative')
    list_filter = ('relationship', 'is_close_relative', 'birthday')
    search_fields = ('user__username', 'user__first_name', 'user__last_name')
    raw_id_fields = ('user',)  # Удобно при большом количестве пользователей

# Также покажем связь в профиле пользователя
class FamilyMemberInline(admin.StackedInline):
    model = FamilyMember
    can_delete = False
    verbose_name_plural = 'Семейная информация'

class UserAdmin(admin.ModelAdmin):
    inlines = (FamilyMemberInline,)

admin.site.unregister(User)
admin.site.register(User, UserAdmin)
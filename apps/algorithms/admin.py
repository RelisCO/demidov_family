from django.contrib import admin
from .models import StepPaymentAlgorithm, MoneyDeductionLog

@admin.register(StepPaymentAlgorithm)
class StepPaymentAlgorithmAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'kilometers', 'amount_earned', 'created_at')
    list_filter = ('created_at', 'user')
    search_fields = ('user__username', 'user__first_name', 'user__last_name')
    readonly_fields = ('created_at',)
    
    # УДАЛИТЬ эти поля, так как их больше нет в модели:
    # readonly_fields = ('created_at', 'processed_at')  # processed_at удален
    # list_display = ('user', 'kilometers', 'amount_earned', 'processed', 'created_at')
    # list_filter = ('processed', 'created_at')
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('user', 'kilometers', 'amount_earned')
        }),
        ('Дополнительная информация', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    def has_add_permission(self, request):
        return True  # Разрешаем добавлять через админку

@admin.register(MoneyDeductionLog)
class MoneyDeductionLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'amount', 'deducted_by', 'created_at')
    list_filter = ('created_at', 'user', 'deducted_by')
    search_fields = ('user__username', 'reason', 'deducted_by__username')
    readonly_fields = ('created_at', 'balance_before', 'balance_after')
    
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
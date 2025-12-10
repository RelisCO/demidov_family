from django.db import models
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

class Transaction(models.Model):
    """Модель транзакций для пополнений и вычетов"""
    
    TRANSACTION_TYPES = [
        ('income', 'Пополнение'),
        ('deduction', 'Вычет'),
        ('step_payment', 'Оплата за шаги'),
        ('other', 'Другое'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Ожидает'),
        ('approved', 'Подтверждено'),
        ('rejected', 'Отклонено'),
        ('cancelled', 'Отменено'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transactions', verbose_name="Пользователь")
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES, verbose_name="Тип транзакции")
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Сумма (£)")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="Статус")
    
    # Описание
    description = models.TextField(verbose_name="Описание", blank=True)
    reason = models.TextField(verbose_name="Причина/Комментарий", blank=True)
    
    # Баланс
    balance_before = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Баланс до", null=True, blank=True)
    balance_after = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Баланс после", null=True, blank=True)
    
    # Временные метки
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    processed_at = models.DateTimeField(null=True, blank=True, verbose_name="Дата обработки")
    processed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, 
                                     related_name='processed_transactions', verbose_name="Обработано")
    
    class Meta:
        verbose_name = "Транзакция"
        verbose_name_plural = "Транзакции"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.username} - {self.get_transaction_type_display()} - {self.amount}£"
    
    def get_status_color(self):
        """Цвет для статуса"""
        colors = {
            'pending': 'warning',
            'approved': 'success',
            'rejected': 'danger',
            'cancelled': 'secondary',
        }
        return colors.get(self.status, 'secondary')
    
    def get_type_color(self):
        """Цвет для типа транзакции"""
        colors = {
            'income': 'success',
            'deduction': 'danger',
            'step_payment': 'info',
            'other': 'secondary',
        }
        return colors.get(self.transaction_type, 'secondary')
    
    def approve(self, user):
        """Подтвердить транзакцию"""
        if self.status == 'pending':
            # Обновляем баланс пользователя
            self.user.profile.virtual_balance += self.amount
            self.user.profile.save()
            
            # Обновляем транзакцию
            self.status = 'approved'
            self.processed_by = user
            self.processed_at = timezone.now()
            self.balance_before = self.user.profile.virtual_balance - self.amount
            self.balance_after = self.user.profile.virtual_balance
            self.save()
            return True
        return False
    
    def reject(self, user, reason=""):
        """Отклонить транзакцию"""
        if self.status == 'pending':
            self.status = 'rejected'
            self.processed_by = user
            self.processed_at = timezone.now()
            self.reason = reason if reason else self.reason
            self.save()
            return True
        return False
    
    def save(self, *args, **kwargs):
        """Автоматически обновляем баланс пользователя"""
        if not self.pk:  # Новая транзакция
            self.balance_before = self.user.profile.virtual_balance
            
            if self.status == 'completed':
                self.balance_after = self.balance_before + self.amount
            else:
                self.balance_after = self.balance_before
        super().save(*args, **kwargs)
    
    def get_icon_class(self):
        """Получить класс иконки для типа транзакции"""
        icons = {
            'step_payment': 'fas fa-walking text-success',
            'money_deduction': 'fas fa-minus-circle text-danger',
            'correction': 'fas fa-exchange-alt text-warning',
            'refund': 'fas fa-undo text-info',
            'other': 'fas fa-question-circle text-secondary',
        }
        return icons.get(self.transaction_type, 'fas fa-question-circle')
    
    def get_badge_class(self):
        """Получить класс для бейджа"""
        classes = {
            'step_payment': 'bg-success',
            'money_deduction': 'bg-danger',
            'correction': 'bg-warning',
            'refund': 'bg-info',
            'other': 'bg-secondary',
        }
        return classes.get(self.transaction_type, 'bg-secondary')
    
    def get_status_badge_class(self):
        """Получить класс для бейджа статуса"""
        classes = {
            'pending': 'bg-warning',
            'completed': 'bg-success',
            'cancelled': 'bg-danger',
            'refunded': 'bg-info',
        }
        return classes.get(self.status, 'bg-secondary')
    
    def process(self, user):
        """Обработать транзакцию"""
        if self.status == 'pending':
            # Обновляем баланс пользователя
            self.user.profile.virtual_balance += self.amount
            self.user.profile.save()
            
            # Обновляем транзакцию
            self.status = 'completed'
            self.processed_by = user
            self.processed_at = timezone.now()
            self.balance_after = self.user.profile.virtual_balance
            self.save()
            return True
        return False
    
    def cancel(self, user, reason=""):
        """Отменить транзакцию"""
        if self.status == 'completed':
            # Возвращаем деньги
            self.user.profile.virtual_balance -= self.amount
            self.user.profile.save()
            
            self.status = 'cancelled'
            self.cancelled_at = timezone.now()
            self.reason = reason
            self.save()
            return True
        return False
    
    def soft_delete(self, user, reason=""):
        """Мягкое удаление транзакции"""
        self.is_deleted = True
        self.save()
        
        # Создаем запись в логе удалений
        TransactionDeletionLog.objects.create(
            transaction=self,
            deleted_by=user,
            reason=reason
        )

class TransactionDeletionLog(models.Model):
    """Лог удаления транзакций"""
    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, 
                                    related_name='deletion_logs', verbose_name="Транзакция")
    deleted_by = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Удалено пользователем")
    reason = models.TextField(verbose_name="Причина удаления")
    deleted_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата удаления")
    
    # Сохраняем оригинальные данные
    original_data = models.JSONField(verbose_name="Оригинальные данные", default=dict)
    
    class Meta:
        verbose_name = "Лог удаления транзакции"
        verbose_name_plural = "Логи удаления транзакций"
        ordering = ['-deleted_at']
    
    def __str__(self):
        return f"Удаление транзакции #{self.transaction.id}"
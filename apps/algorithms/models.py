from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models.signals import pre_delete
from django.dispatch import receiver



class MoneyDeductionLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='deductions', verbose_name="Пользователь")
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Сумма вычета (£)")
    reason = models.TextField(verbose_name="Причина вычета")
    deducted_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='made_deductions', 
                                    verbose_name="Вычет произведен")
    balance_before = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Баланс до вычета")
    balance_after = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Баланс после вычета")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата вычета")
    is_deleted = models.BooleanField(default=False, verbose_name="Удалено")
    deleted_at = models.DateTimeField(null=True, blank=True, verbose_name="Дата удаления")
    deleted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='deleted_deductions', verbose_name="Удалено пользователем")
    delete_reason = models.TextField(verbose_name="Причина удаления", blank=True)
    
    class Meta:
        verbose_name = "Лог вычета денег"
        verbose_name_plural = "Логи вычетов денег"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.username} - {self.amount}£ - {self.created_at.strftime('%d.%m.%Y')}"
    
    def soft_delete(self, user, reason=""):
        """Мягкое удаление записи о вычете"""
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.deleted_by = user
        self.delete_reason = reason
        self.save()
        
        # Возвращаем деньги пользователю
        try:
            self.user.profile.add_money(
                amount=self.amount,
                reason=f"Отмена вычета (удаление записи #{self.id}): {reason}",
                transaction_type='income'
            )
        except Exception as e:
            # Логируем ошибку, но продолжаем удаление
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error reverting deduction #{self.id}: {str(e)}")


    def save(self, *args, **kwargs):
        """При сохранении создаем транзакцию"""
        if not self.pk:  # Новая запись
            # Создаем транзакцию вычета
            transaction = self.user.profile.create_transaction(
                amount=-self.amount,  # Отрицательная сумма для вычета
                transaction_type='money_deduction',
                description=self.reason,
                algorithm='money_deduction',
                source_id=self.id,
                created_by=self.deducted_by,
                requires_approval=False
            )
            
            # Обрабатываем транзакцию
            transaction.process(self.deducted_by)
        
        super().save(*args, **kwargs)

class StepPaymentAlgorithm(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Пользователь")
    kilometers = models.DecimalField(max_digits=6, decimal_places=2, verbose_name="Километры")
    amount_earned = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Заработано (£)")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    
    class Meta:
        verbose_name = "Алгоритм оплаты за шаги"
        verbose_name_plural = "Алгоритмы оплаты за шаги"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.username} - {self.kilometers}км - {self.amount_earned}£"
    
    def create_transaction(self, created_by_user):
        """Создать транзакцию для этой выплаты - УПРОЩЕННАЯ ВЕРСИЯ БЕЗ ИМПОРТА"""
        # Просто обновляем баланс пользователя без транзакций
        self.user.profile.virtual_balance += self.amount_earned
        self.user.profile.total_earned += self.amount_earned
        self.user.profile.steps_balance += int(self.kilometers * 1000)
        self.user.profile.save()
        
        return True  # Возвращаем успех
    

    
class PaymentDeletionLog(models.Model):
    payment = models.ForeignKey(StepPaymentAlgorithm, on_delete=models.CASCADE, 
                                related_name='deletion_logs', verbose_name="Удаленная запись")
    deleted_by = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Удалено пользователем")
    reason = models.TextField(verbose_name="Причина удаления")
    deleted_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата удаления")
    
    # Сохраняем оригинальные данные на случай если запись будет полностью удалена
    original_amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Оригинальная сумма")
    original_user = models.ForeignKey(User, on_delete=models.CASCADE, 
                                      related_name='deleted_payment_logs', verbose_name="Оригинальный пользователь")
    original_created_at = models.DateTimeField(verbose_name="Оригинальная дата создания")
    
    class Meta:
        verbose_name = "Лог удаления выплаты"
        verbose_name_plural = "Логи удаления выплат"
        ordering = ['-deleted_at']
    
    def __str__(self):
        return f"Удаление записи #{self.payment.id} - {self.deleted_at.strftime('%d.%m.%Y %H:%M')}"

# Сигнал для отката транзакции при удалении обработанной выплаты
@receiver(pre_delete, sender=StepPaymentAlgorithm)
def revert_payment_on_delete(sender, instance, **kwargs):
    """Откат транзакции при удалении обработанной выплаты"""
    if instance.processed and not instance.is_deleted:
        try:
            # Вычитаем сумму из баланса пользователя
            profile = instance.user.profile
            profile.virtual_balance -= instance.amount_earned
            profile.total_earned -= instance.amount_earned
            profile.steps_balance -= int(instance.kilometers * 1000)
            profile.save()
            
            # Создаем запись о возврате
            from apps.users.models import Transaction
            Transaction.objects.create(
                user=instance.user,
                amount=instance.amount_earned,
                transaction_type='deduction',
                balance_after=profile.virtual_balance,
                reason=f"Отмена выплаты (удаление записи #{instance.id})"
            )
        except Exception as e:
            # Логируем ошибку, но не прерываем удаление
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error reverting payment #{instance.id}: {str(e)}")
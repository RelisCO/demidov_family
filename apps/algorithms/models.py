from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from decimal import Decimal
from typing import Optional
from django.apps import apps
from datetime import date

class MoneyDeductionLog(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='deductions', verbose_name="Пользователь"
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Сумма вычета (£)")
    reason = models.TextField(verbose_name="Причина вычета")
    deducted_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='made_deductions', verbose_name="Вычет произведен"
    )
    balance_before = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Баланс до вычета")
    balance_after = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Баланс после вычета")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата вычета")
    is_deleted = models.BooleanField(default=False, verbose_name="Удалено")
    deleted_at = models.DateTimeField(null=True, blank=True, verbose_name="Дата удаления")
    deleted_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='deleted_deductions', verbose_name="Удалено пользователем"
    )
    delete_reason = models.TextField(verbose_name="Причина удаления", blank=True)

    class Meta:
        verbose_name = "Лог вычета денег"
        verbose_name_plural = "Логи вычетов денег"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['is_deleted', 'created_at']),
        ]

    def __str__(self) -> str:
        return f"{self.user.username} - {self.amount}£ - {self.created_at.strftime('%d.%m.%Y')}"

    def soft_delete(self, user: User, reason: str = "") -> None:
        """Мягкое удаление записи с откатом вычета."""
        if self.is_deleted:
            return

        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.deleted_by = user
        self.delete_reason = reason
        self.save(update_fields=[
            'is_deleted', 'deleted_at', 'deleted_by', 'delete_reason'
        ])

        # Возврат средств пользователю
        self._revert_deduction(reason)

    def _revert_deduction(self, reason: str) -> None:
        """Возвращает деньги пользователю после удаления вычета."""
        try:
            profile = self.user.profile
            profile.add_money(
                amount=self.amount,
                reason=f"Отмена вычета (удаление записи #{self.id}): {reason}",
                transaction_type='income'
            )
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Ошибка при откате вычета #{self.id}: {str(e)}", exc_info=True)

    def save(self, *args, **kwargs) -> None:
        """Создаёт транзакцию при первом сохранении."""
        is_new = not self.pk
        super().save(*args, **kwargs)

        if is_new:
            self._create_deduction_transaction()

    def _create_deduction_transaction(self) -> None:
        """Создаёт транзакцию вычета средств."""
        try:
            transaction = self.user.profile.create_transaction(
                amount=-self.amount,
                transaction_type='money_deduction',
                description=self.reason,
                algorithm='money_deduction',
                source_id=self.pk,
                created_by=self.deducted_by,
                requires_approval=False
            )
            transaction.process(self.deducted_by)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Ошибка при создании транзакции вычета #{self.id}: {str(e)}", exc_info=True)


class StepPaymentAlgorithm(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Пользователь")
    kilometers = models.DecimalField(max_digits=6, decimal_places=2, verbose_name="Километры")
    amount_earned = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Заработано (£)")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    processed = models.BooleanField(default=True, verbose_name="Обработано")
    is_deleted = models.BooleanField(default=False, verbose_name="Удалено")

    class Meta:
        verbose_name = "Алгоритм оплаты за шаги"
        verbose_name_plural = "Алгоритмы оплаты за шаги"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'processed']),
            models.Index(fields=['is_deleted', 'created_at']),
        ]

    def __str__(self) -> str:
        return f"{self.user.username} - {self.kilometers}км - {self.amount_earned}£"

    def create_transaction(self, created_by_user: User) -> bool:
        """Создаёт транзакцию и обновляет профиль."""
        if not self.processed:
            try:
                self._apply_payment()
                self.processed = True
                self.save(update_fields=['processed'])
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Ошибка при начислении выплаты за шаги #{self.id}: {str(e)}", exc_info=True)
                return False
        return True

    def _apply_payment(self) -> None:
        """Начисление средств пользователю."""
        profile = self.user.profile
        profile.virtual_balance += self.amount_earned
        profile.total_earned += self.amount_earned
        profile.steps_balance += int(self.kilometers * 1000)
        profile.save(update_fields=['virtual_balance', 'total_earned', 'steps_balance'])


class PaymentDeletionLog(models.Model):
    payment = models.ForeignKey(
        StepPaymentAlgorithm, on_delete=models.CASCADE, related_name='deletion_logs', verbose_name="Удаленная запись"
    )
    deleted_by = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Удалено пользователем")
    reason = models.TextField(verbose_name="Причина удаления")
    deleted_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата удаления")

    # Сохранение данных на случай восстановления
    original_amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Оригинальная сумма")
    original_user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='deleted_payment_logs', verbose_name="Оригинальный пользователь"
    )
    original_created_at = models.DateTimeField(verbose_name="Оригинальная дата создания")

    class Meta:
        verbose_name = "Лог удаления выплаты"
        verbose_name_plural = "Логи удаления выплат"
        ordering = ['-deleted_at']
        indexes = [
            models.Index(fields=['payment']),
            models.Index(fields=['original_user', '-deleted_at']),
        ]

    def __str__(self) -> str:
        return f"Удаление записи #{self.payment.id} - {self.deleted_at.strftime('%d.%m.%Y %H:%M')}"


# Сигнал: откат выплаты при удалении
@receiver(pre_delete, sender=StepPaymentAlgorithm)
def revert_payment_on_delete(sender, instance: StepPaymentAlgorithm, **kwargs) -> None:
    """Откат начисления при удалении обработанной записи."""
    if not instance.processed or instance.is_deleted:
        return

    try:
        profile = instance.user.profile
        # Откат изменений баланса
        profile.virtual_balance = (profile.virtual_balance - instance.amount_earned).quantize(Decimal('0.01'))
        profile.total_earned = (profile.total_earned - instance.amount_earned).quantize(Decimal('0.01'))
        profile.steps_balance = max(0, profile.steps_balance - int(instance.kilometers * 1000))
        profile.save(update_fields=['virtual_balance', 'total_earned', 'steps_balance'])

        # Фиксация отката в виде транзакции
        Transaction = apps.get_model('users', 'Transaction')
        
        Transaction.objects.create(
            user=instance.user,
            amount=instance.amount_earned,
            transaction_type='deduction',
            balance_after=profile.virtual_balance,
            reason=f"Отмена выплаты (удаление записи #{instance.id})"
        )

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Ошибка при откате выплаты #{instance.id}: {str(e)}", exc_info=True)



class FamilyMember(models.Model):
    RELATIONSHIP_TYPES = [
        ('parent', 'Родитель'),
        ('child', 'Ребёнок'),
        ('sibling', 'Брат/сестра'),
        ('cousin', 'Двоюродный брат/сестра'),
        ('aunt_uncle', 'Тётя/дядя'),
        ('other', 'Другое'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='family_info')
    relationship = models.CharField(max_length=20, choices=RELATIONSHIP_TYPES)
    birthday = models.DateField(verbose_name="Дата рождения")
    is_close_relative = models.BooleanField(default=False, help_text="Близкий родственник: родители, дети, братья/сёстры")

    @classmethod
    def get_today_birthdays(cls):
        """Возвращает всех, у кого сегодня день рождения"""
        today = date.today()
        return cls.objects.filter(
            birthday__month=today.month,
            birthday__day=today.day
        )

    def __str__(self):
        return f"{self.user.username} — {self.get_relationship_display()}"

    class Meta:
        verbose_name = "Семейный член"
        verbose_name_plural = "Семейные члены"
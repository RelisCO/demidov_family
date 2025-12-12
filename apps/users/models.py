# apps/users/models.py
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.validators import MinValueValidator
from decimal import Decimal
from django.utils import timezone


class UserProfile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile',
        verbose_name="Пользователь"
    )
    virtual_balance = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Виртуальный баланс (£)",
        validators=[MinValueValidator(0)]
    )
    steps_balance = models.IntegerField(
        default=0,
        verbose_name="Общее количество шагов"
    )
    total_earned = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Всего заработано (£)",
        validators=[MinValueValidator(0)]
    )
    total_deducted = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Всего вычтено (£)",
        validators=[MinValueValidator(0)]
    )

    class Meta:
        verbose_name = "Профиль пользователя"
        verbose_name_plural = "Профили пользователей"

    def __str__(self):
        full_name = self.user.get_full_name()
        return f"{full_name if full_name else self.user.username} - {self.virtual_balance}£"

    def create_transaction(self, amount, transaction_type, description="", reason="",
                           algorithm="", source_id=None, created_by=None, requires_approval=False):
        """
        Создать новую транзакцию.
        Обеспечивает атомарность: баланс обновляется только при успешном создании транзакции.
        """
        from apps.transactions.models import Transaction

        # Убедимся, что amount — это Decimal
        amount = Decimal(amount)

        # Расчёт нового баланса
        balance_before = self.virtual_balance
        balance_after = balance_before + amount if amount >= 0 else balance_before - abs(amount)

        transaction = Transaction.objects.create(
            user=self.user,
            amount=amount,
            transaction_type=transaction_type,
            description=description,
            reason=reason,
            algorithm=algorithm,
            source_id=source_id,
            created_by=created_by,
            requires_approval=requires_approval,
            balance_before=balance_before,
            balance_after=balance_after,
            metadata={
                'user_id': self.user.id,
                'profile_id': self.id,
            }
        )

        # Если не требует подтверждения — сразу обрабатываем
        if not requires_approval:
            transaction.process(created_by or self.user)

        return transaction

    def add_money(self, amount, transaction_type="income", description="", reason="",
                  algorithm="", source_id=None, created_by=None):
        """Добавить деньги через транзакцию с корректным типом."""
        amount = Decimal(amount)
        if amount < 0:
            raise ValueError("Сумма пополнения не может быть отрицательной.")

        # Определение типа транзакции
        if transaction_type == "income":
            transaction_type = "step_payment" if algorithm == "step_payment" else "other_income"
        elif transaction_type == "deduction":
            transaction_type = "money_deduction"
        else:
            transaction_type = "other_income"

        return self.create_transaction(
            amount=amount,
            transaction_type=transaction_type,
            description=description,
            reason=reason,
            algorithm=algorithm,
            source_id=source_id,
            created_by=created_by,
            requires_approval=False
        )

    def deduct_money(self, amount, reason="", created_by=None):
        """Вычесть деньги через транзакцию с проверкой баланса."""
        amount = Decimal(amount)
        if amount <= 0:
            raise ValueError("Сумма вычета должна быть положительной.")

        if self.virtual_balance < amount:
            raise ValueError(f"Недостаточно средств. Баланс: {self.virtual_balance}£, требуется: {amount}£")

        # Обновляем баланс
        self.virtual_balance -= amount
        self.total_deducted += amount
        self.save(update_fields=['virtual_balance', 'total_deducted'])

        # Создаём транзакцию
        try:
            from apps.transactions.models import Transaction

            Transaction.objects.create(
                user=self.user,
                amount=-amount,
                transaction_type='money_deduction',
                description=reason,
                reason=reason,
                algorithm='manual_deduction',
                created_by=created_by,
                requires_approval=False,
                balance_before=self.virtual_balance + amount,
                balance_after=self.virtual_balance,
                status='completed',
                processed_by=created_by,
                processed_at=timezone.now()
            )
        except (ImportError, Exception) as e:
            # Логируем ошибку, если транзакции недоступны
            import logging
            logging.getLogger("UserProfile").warning(f"Не удалось создать транзакцию для вычета: {e}")

        return True


@receiver(post_save, sender=User)
def create_or_save_user_profile(sender, instance, created, **kwargs):
    """
    Единый обработчик для создания и сохранения профиля.
    Исключает двойные вызовы и улучшает производительность.
    """
    if created:
        UserProfile.objects.create(user=instance)
    else:
        if hasattr(instance, 'profile'):
            instance.profile.save()

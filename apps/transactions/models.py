# ... импорты ...
from django.db import models
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
import json

class Transaction(models.Model):
    """Модель транзакций для пополнений и вычетов"""

    TRANSACTION_TYPES = [
        ('income', _('Пополнение')),
        ('deduction', _('Вычет')),
        ('step_payment', _('Оплата за шаги')),
        ('other', _('Другое')),
    ]

    STATUS_CHOICES = [
        ('pending', _('Ожидает')),
        ('approved', _('Подтверждено')),
        ('rejected', _('Отклонено')),
        ('cancelled', _('Отменено')),
    ]

    # Основные поля
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='transactions',
        verbose_name=_("Пользователь")
    )
    transaction_type = models.CharField(
        max_length=20,
        choices=TRANSACTION_TYPES,
        verbose_name=_("Тип транзакции")
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name=_("Сумма (£)")
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name=_("Статус")
    )

    # Описание
    description = models.TextField(
        verbose_name=_("Описание"),
        blank=True
    )
    reason = models.TextField(
        verbose_name=_("Причина/Комментарий"),
        blank=True
    )

    # Баланс
    balance_before = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name=_("Баланс до"),
        null=True,
        blank=True
    )
    balance_after = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name=_("Баланс после"),
        null=True,
        blank=True
    )

    # Временные метки
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Дата создания")
    )
    processed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Дата обработки")
    )
    processed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='processed_transactions',
        verbose_name=_("Обработано")
    )

    # Поле для мягкого удаления
    is_deleted = models.BooleanField(
        default=False,
        verbose_name=_("Удалено"),
        db_index=True
    )

    class Meta:
        verbose_name = _("Транзакция")
        verbose_name_plural = _("Транзакции")
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status', 'is_deleted']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.get_transaction_type_display()} - {self.amount}£"

    def get_status_color(self):
        """Цвет статуса для интерфейса"""
        colors = {
            'pending': 'warning',
            'approved': 'success',
            'rejected': 'danger',
            'cancelled': 'secondary',
        }
        return colors.get(self.status, 'secondary')

    def get_type_color(self):
        """Цвет типа транзакции"""
        colors = {
            'income': 'success',
            'deduction': 'danger',
            'step_payment': 'info',
            'other': 'secondary',
        }
        return colors.get(self.transaction_type, 'secondary')

    def get_icon_class(self):
        """Иконка для типа транзакции"""
        icons = {
            'income': 'fas fa-plus-circle text-success',
            'deduction': 'fas fa-minus-circle text-danger',
            'step_payment': 'fas fa-walking text-info',
            'other': 'fas fa-question-circle text-secondary',
        }
        return icons.get(self.transaction_type, 'fas fa-question-circle')

    def get_badge_class(self):
        """Бейдж для типа транзакции"""
        classes = {
            'income': 'bg-success',
            'deduction': 'bg-danger',
            'step_payment': 'bg-info',
            'other': 'bg-secondary',
        }
        return classes.get(self.transaction_type, 'bg-secondary')

    def get_status_badge_class(self):
        """Бейдж для статуса транзакции"""
        classes = {
            'pending': 'bg-warning text-dark',
            'approved': 'bg-success',
            'rejected': 'bg-danger',
            'cancelled': 'bg-secondary',
        }
        return classes.get(self.status, 'bg-secondary')

    def save(self, *args, **kwargs):
        """Автоматическое сохранение баланса при создании транзакции"""
        if not self.pk:  # Новая транзакция
            profile = self.user.profile
            self.balance_before = profile.virtual_balance
            if self.status == 'approved':
                self.balance_after = self.balance_before + self.amount
            else:
                self.balance_after = self.balance_before
        super().save(*args, **kwargs)

    def approve(self, processed_by):
        """Подтвердить транзакцию"""
        if self.status != 'pending':
            return False

        profile = self.user.profile
        self.status = 'approved'
        self.processed_by = processed_by
        self.processed_at = timezone.now()
        self.balance_before = profile.virtual_balance
        profile.virtual_balance += self.amount
        self.balance_after = profile.virtual_balance

        profile.save()
        self.save()
        return True

    def reject(self, processed_by, reason=""):
        """Отклонить транзакцию"""
        if self.status != 'pending':
            return False

        self.status = 'rejected'
        self.processed_by = processed_by
        self.processed_at = timezone.now()
        if reason:
            self.reason = reason
        self.save()
        return True

    def cancel(self, cancelled_by, reason=""):
        """Отменить подтверждённую транзакцию и вернуть средства"""
        if self.status != 'approved':
            return False

        profile = self.user.profile
        profile.virtual_balance -= self.amount
        profile.save()

        self.status = 'cancelled'
        self.processed_by = cancelled_by
        self.processed_at = timezone.now()
        self.reason = reason
        self.save()
        return True

    def soft_delete(self, deleted_by, reason=""):
        """Мягкое удаление транзакции с логированием"""
        self.is_deleted = True
        self.save()

        # Сохраняем данные транзакции для аудита
        TransactionDeletionLog.objects.create(
            transaction=self,
            deleted_by=deleted_by,
            reason=reason,
            original_data=self._get_serialized_data()
        )

    def _get_serialized_data(self):
        """Сериализация данных транзакции для лога"""
        return {
            'user_id': self.user.id,
            'username': self.user.username,
            'transaction_type': self.transaction_type,
            'amount': str(self.amount),
            'status': self.status,
            'description': self.description,
            'reason': self.reason,
            'balance_before': str(self.balance_before),
            'balance_after': str(self.balance_after),
            'created_at': self.created_at.isoformat(),
            'processed_at': self.processed_at.isoformat() if self.processed_at else None,
        }


class TransactionDeletionLog(models.Model):
    """Лог удаления транзакций (аудит)"""
    transaction = models.ForeignKey(
        Transaction,
        on_delete=models.CASCADE,
        related_name='deletion_logs',
        verbose_name=_("Транзакция")
    )
    deleted_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        verbose_name=_("Удалено пользователем")
    )
    reason = models.TextField(
        verbose_name=_("Причина удаления"),
        blank=True
    )
    deleted_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Дата удаления")
    )
    original_data = models.JSONField(
        verbose_name=_("Оригинальные данные"),
        default=dict
    )

    class Meta:
        verbose_name = _("Лог удаления транзакции")
        verbose_name_plural = _("Логи удаления транзакций")
        ordering = ['-deleted_at']
        indexes = [
            models.Index(fields=['deleted_by', 'deleted_at']),
        ]

    def __str__(self):
        return f"Удаление транзакции #{self.transaction.id}"

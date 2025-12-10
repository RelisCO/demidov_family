# apps/users/models.py
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.validators import MinValueValidator
from decimal import Decimal
from django.utils import timezone



class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    virtual_balance = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0, 
        verbose_name="Виртуальный баланс (£)",
        validators=[MinValueValidator(0)]
    )
    steps_balance = models.IntegerField(default=0, verbose_name="Общее количество шагов")
    total_earned = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Всего заработано (£)")
    total_deducted = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Всего вычтено (£)")
    
    class Meta:
        verbose_name = "Профиль пользователя"
        verbose_name_plural = "Профили пользователей"
    
    def __str__(self):
        return f"{self.user.get_full_name()} - {self.virtual_balance}£"
    
    def create_transaction(self, amount, transaction_type, description="", reason="", 
                          algorithm="", source_id=None, created_by=None, requires_approval=False):
        """Создать новую транзакцию"""
        from apps.transactions.models import Transaction
        
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
            balance_before=self.virtual_balance,
            balance_after=self.virtual_balance + amount if amount >= 0 else self.virtual_balance,
            metadata={
                'user_id': self.user.id,
                'profile_id': self.id,
            }
        )
        
        # Если не требуется подтверждение, сразу обрабатываем
        if not requires_approval:
            transaction.process(created_by or self.user)
        
        return transaction
    
    def add_money(self, amount, transaction_type="income", description="", reason="", 
                  algorithm="", source_id=None, created_by=None):
        """Добавить или вычесть деньги через транзакцию"""
        if transaction_type == "income":
            transaction_type = "step_payment" if algorithm == "step_payment" else "other"
        elif transaction_type == "deduction":
            transaction_type = "money_deduction"
        
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
        """Вычесть деньги у пользователя"""
        if self.virtual_balance < amount:
            raise ValueError(f"Недостаточно средств. Баланс: {self.virtual_balance}£, требуется: {amount}£")
        
        # Вычитаем деньги
        self.virtual_balance -= amount
        self.total_deducted += amount
        self.save()
        
        # Создаем транзакцию если система транзакций доступна
        try:
            from transactions.models import Transaction
            
            Transaction.objects.create(
                user=self.user,
                amount=-amount,  # Отрицательная сумма
                transaction_type='money_deduction',
                description=reason,
                algorithm='money_deduction',
                created_by=created_by,
                requires_approval=False,
                balance_before=self.virtual_balance + amount,
                balance_after=self.virtual_balance,
                status='completed',
                processed_by=created_by,
                processed_at=timezone.now()
            )
        except ImportError:
            pass
        
        return True

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, 'profile'):
        instance.profile.save()
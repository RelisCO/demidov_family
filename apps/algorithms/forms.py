from django import forms
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from .models import StepPaymentAlgorithm, MoneyDeductionLog
from django.utils import timezone



class StepPaymentForm(forms.Form):
    user = forms.ModelChoiceField(
        queryset=User.objects.all(),
        label="Выберите пользователя",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    kilometers = forms.DecimalField(
        max_digits=6,
        decimal_places=2,
        label="Километры",
        min_value=0.01,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )
    
    def calculate_amount(self):
        """Рассчитать сумму к выплате"""
        if self.is_valid():
            kilometers = self.cleaned_data['kilometers']
            return kilometers * 1
        return 0
    
    def save(self, request=None):
        """Сохранить расчет и создать транзакцию"""
        if self.is_valid():
            user = self.cleaned_data['user']
            kilometers = self.cleaned_data['kilometers']
            amount_earned = kilometers * 1
            
            # Создаем запись алгоритма
            algorithm = StepPaymentAlgorithm.objects.create(
                user=user,
                kilometers=kilometers,
                amount_earned=amount_earned
            )
            
            # Создаем транзакцию в модуле transactions
            if request and request.user.is_authenticated:
                try:
                    # Пробуем импортировать из transactions
                    from transactions.models import Transaction
                    
                    Transaction.objects.create(
                        user=user,
                        transaction_type='step_payment',
                        amount=amount_earned,
                        status='pending',
                        description=f"Оплата за {kilometers} км",
                        reason=f"Создано пользователем {request.user.username}"
                    )
                except ImportError:
                    # Если не получилось, попробуем с префиксом apps
                    try:
                        from apps.transactions.models import Transaction
                        
                        Transaction.objects.create(
                            user=user,
                            transaction_type='step_payment',
                            amount=amount_earned,
                            status='pending',
                            description=f"Оплата за {kilometers} км",
                            reason=f"Создано пользователем {request.user.username}"
                        )
                    except ImportError:
                        # Если транзакции не работают, просто сохраняем алгоритм
                        pass
            
            return algorithm
        return None

class MoneyDeductionForm(forms.Form):
    user = forms.ModelChoiceField(
        queryset=User.objects.all(),
        label="Пользователь",
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'deduction-user'})
    )
    amount = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        label="Сумма вычета (£)",
        min_value=0.01,
        validators=[MinValueValidator(0.01)],
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.01',
            'id': 'deduction-amount'
        })
    )
    reason = forms.CharField(
        label="Причина вычета",
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Опишите причину вычета...',
            'id': 'deduction-reason'
        }),
        required=True
    )
    
    def clean(self):
        cleaned_data = super().clean()
        user = cleaned_data.get('user')
        amount = cleaned_data.get('amount')
        
        if user and amount:
            # Получаем актуальный баланс из базы данных
            user.refresh_from_db()
            current_balance = user.profile.virtual_balance
            
            if current_balance < amount:
                raise forms.ValidationError(
                    f"Недостаточно средств у пользователя '{user.get_full_name()}'. "
                    f"Текущий баланс: {current_balance}£, требуется: {amount}£"
                )
            
            # Сохраняем актуальный баланс для использования в save()
            cleaned_data['current_balance'] = current_balance
        
        return cleaned_data
    
    def save(self, request):
        """Выполнить вычет"""
        if self.is_valid():
            user = self.cleaned_data['user']
            amount = self.cleaned_data['amount']
            reason = self.cleaned_data['reason']
            
            try:
                # Создаем транзакцию вычета в модуле transactions
                try:
                    from transactions.models import Transaction
                except ImportError:
                    from apps.transactions.models import Transaction
                
                transaction = Transaction.objects.create(
                    user=user,
                    transaction_type='deduction',
                    amount=-amount,  # Отрицательная сумма для вычета
                    status='pending',
                    description=f"Вычет денег",
                    reason=reason
                )
                
                # Создаем лог вычета
                MoneyDeductionLog.objects.create(
                    user=user,
                    amount=amount,
                    reason=reason,
                    deducted_by=request.user,
                    balance_before=user.profile.virtual_balance,
                    balance_after=user.profile.virtual_balance - amount
                )
                
                return True, f"Создана транзакция на вычет {amount}£. Ожидает подтверждения."
                
            except Exception as e:
                return False, f"Ошибка: {str(e)}"
        
        return False, "Ошибка валидации формы"
        

class DeletePaymentForm(forms.Form):
    reason = forms.CharField(
        label="Причина удаления",
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Обязательно укажите причину удаления записи...',
            'required': True
        }),
        help_text="Объясните, почему вы удаляете эту запись"
    )
    
    restore_money = forms.BooleanField(
        label="Вернуть деньги пользователю",
        required=False,
        initial=True,
        help_text="Если отмечено, сумма будет вычтена из баланса пользователя"
    )
    
    def __init__(self, *args, **kwargs):
        self.payment = kwargs.pop('payment', None)
        super().__init__(*args, **kwargs)
        
        if self.payment and not self.payment.processed:
            # Для необработанных выплат деньги не нужно возвращать
            self.fields['restore_money'].initial = False
            self.fields['restore_money'].help_text = "Запись не была обработана, деньги не начислялись"

class DeleteDeductionForm(forms.Form):
    reason = forms.CharField(
        label="Причина удаления",
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Обязательно укажите причину удаления записи...',
            'required': True
        }),
        help_text="Объясните, почему вы удаляете эту запись вычета"
    )
    
    restore_money = forms.BooleanField(
        label="Вернуть деньги пользователю",
        required=False,
        initial=True,
        help_text="Если отмечено, сумма вычета будет возвращена на баланс пользователя"
    )
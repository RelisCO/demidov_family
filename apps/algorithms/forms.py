from django import forms
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.utils import timezone
from importlib import import_module
from .models import FamilyMember
from .models import StepPaymentAlgorithm, MoneyDeductionLog


def get_transaction_model():
    """Безопасный импорт модели Transaction из модуля transactions"""
    for app_prefix in ['', 'apps.']:
        try:
            transactions_app = import_module(f"{app_prefix}transactions.models")
            return transactions_app.Transaction
        except ImportError:
            continue
    return None


class StepPaymentForm(forms.Form):
    user = forms.ModelChoiceField(
        queryset=User.objects.select_related('profile'),
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
        """Рассчитать сумму к выплате (фиксированная ставка 1£/км)"""
        if self.is_valid():
            return self.cleaned_data['kilometers'] * 1
        return 0

    def save(self, request=None):
        """Сохранить расчет и создать транзакцию"""
        if not self.is_valid():
            return None

        user = self.cleaned_data['user']
        kilometers = self.cleaned_data['kilometers']
        amount_earned = kilometers * 1

        # Создаем запись алгоритма
        algorithm = StepPaymentAlgorithm.objects.create(
            user=user,
            kilometers=kilometers,
            amount_earned=amount_earned
        )

        # Создаем транзакцию, если возможно
        Transaction = get_transaction_model()
        if Transaction and request and request.user.is_authenticated:
            try:
                Transaction.objects.create(
                    user=user,
                    transaction_type='step_payment',
                    amount=amount_earned,
                    status='pending',
                    description=f"Оплата за {kilometers} км",
                    reason=f"Создано пользователем {request.user.username}"
                )
            except Exception as e:
                # Логирование ошибки транзакции (желательно добавить logger)
                pass  # Игнорируем, но в продакшене — залогируйте

        return algorithm


class MoneyDeductionForm(forms.Form):
    user = forms.ModelChoiceField(
        queryset=User.objects.select_related('profile'),
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

        if not user or not amount:
            return cleaned_data

        # Обновляем данные пользователя из БД
        try:
            user.refresh_from_db()
            current_balance = user.profile.virtual_balance
        except User.profile.RelatedObjectDoesDoesNotExist:
            raise forms.ValidationError("У пользователя отсутствует профиль.")
        except AttributeError:
            raise forms.ValidationError("Профиль пользователя не содержит virtual_balance.")

        if current_balance < amount:
            raise forms.ValidationError(
                f"Недостаточно средств у пользователя '{user.get_full_name() or user.username}'. "
                f"Текущий баланс: {current_balance}£, требуется: {amount}£"
            )

        cleaned_data['current_balance'] = current_balance
        return cleaned_data

    def save(self, request):
        """Создать вычет и запись в лог"""
        if not self.is_valid():
            return False, "Ошибка валидации формы"

        user = self.cleaned_data['user']
        amount = self.cleaned_data['amount']
        reason = self.cleaned_data['reason']

        Transaction = get_transaction_model()
        if not Transaction:
            return False, "Модуль транзакций недоступен."

        try:
            # Создаём транзакцию
            transaction = Transaction.objects.create(
                user=user,
                transaction_type='deduction',
                amount=-amount,
                status='pending',
                description="Вычет денег",
                reason=reason
            )

            # Логируем вычет
            MoneyDeductionLog.objects.create(
                user=user,
                amount=amount,
                reason=reason,
                deducted_by=request.user,
                balance_before=self.cleaned_data['current_balance'],
                balance_after=self.cleaned_data['current_balance'] - amount
            )

            return True, f"Создана транзакция на вычет {amount}£. Ожидает подтверждения."

        except Exception as e:
            return False, f"Ошибка при создании вычета: {str(e)}"


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
        help_text="Если отмечено, сумма будет возвращена на баланс пользователя"
    )

    def __init__(self, *args, **kwargs):
        self.payment = kwargs.pop('payment', None)
        super().__init__(*args, **kwargs)

        if self.payment and not self.payment.processed:
            self.fields['restore_money'].initial = False
            self.fields['restore_money'].help_text = "Запись не была обработана, деньги не начислялись"


class DeleteDeductionForm(forms.Form):
    reason = forms.CharField(
        label="Причина удаления",
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Обязательно укажите причину удаления записи вычета...',
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




# forms.py
from django import forms
from .models import FamilyMember

# forms.py
class BirthdayRewardForm(forms.Form):
    birthday_person = forms.ModelChoiceField(
        queryset=FamilyMember.objects.none(),
        label="Именинник",
        empty_label="--- Выберите именинника ---",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        today = FamilyMember.get_today_birthdays()
        # Если нет именинников сегодня — показываем всех
        queryset = today if today.exists() else FamilyMember.objects.all()

        # Сортируем по ФИО
        self.fields['birthday_person'].queryset = queryset.select_related('user').order_by('user__last_name', 'user__first_name')

        # Кастомизируем отображение: "Имя Фамилия (логин)" или только ФИО
        self.fields['birthday_person'].label_from_instance = self.get_full_name_label

    def get_full_name_label(self, obj):
        """Возвращает 'Имя Фамилия' или 'логин', если ФИО нет"""
        full_name = obj.user.get_full_name().strip()
        if full_name:
            return full_name
        return obj.user.username  # fallback


class BirthdayGuestAttendanceForm(forms.Form):
    ATTENDANCE_CHOICES = [
        ('in_person', 'Лично'),
        ('online', 'Телемост'),
        ('absent', 'Отсутствовал'),
    ]

    def __init__(self, *args, **kwargs):
        attendees = kwargs.pop('attendees', None)
        birthday_person = kwargs.pop('birthday_person', None)  # Передадим именинника
        super().__init__(*args, **kwargs)

        if attendees and birthday_person:
            for user in attendees:
                # Проверим, ребёнок ли он и близкий родственник
                is_attending_child = False
                try:
                    fm = user.family_info
                    if fm.relationship == 'child' and fm.is_close_relative and birthday_person.relationship == 'parent':
                        is_attending_child = True
                except:
                    pass

                # Поле: формат участия
                attendance_field_name = f'attendance_{user.id}'
                self.fields[attendance_field_name] = forms.ChoiceField(
                    label=f"{user.get_full_name() or user.username}",
                    choices=self.ATTENDANCE_CHOICES,
                    widget=forms.RadioSelect,
                    initial='absent',
                    required=True
                )

                # Если это ребёнок, и именинник — родитель → добавляем поле "комбо лет"
                if is_attending_child:
                    combo_field_name = f'combo_years_{user.id}'
                    self.fields[combo_field_name] = forms.IntegerField(
                        label="✅ Комбо лет (без пропусков)",
                        min_value=0,
                        max_value=50,
                        initial=1,
                        required=False,
                        widget=forms.NumberInput(attrs={'class': 'form-control-combo'})
                    )
                    # Связываем с пользователем
                    self.fields[combo_field_name].user_id = user.id

    def get_attendance_for_user(self, user_id):
        return self.cleaned_data.get(f'attendance_{user_id}')

    def get_combo_years_for_user(self, user_id):
        field_name = f'combo_years_{user_id}'
        if field_name in self.fields:
            val = self.cleaned_data.get(field_name)
            return val if val is not None else 0
        return 0

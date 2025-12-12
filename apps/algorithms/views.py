from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.db.models import Sum, F, Q
from .forms import BirthdayGuestAttendanceForm, StepPaymentForm, MoneyDeductionForm, DeletePaymentForm, DeleteDeductionForm
from .models import StepPaymentAlgorithm, MoneyDeductionLog, PaymentDeletionLog



from django.db import transaction as db_transaction
from .forms import BirthdayRewardForm
from .models import FamilyMember
from apps.transactions.models import Transaction  # ← Правильный путь




def algorithms(request):
    """Главная страница алгоритмов"""
    recent_calculations = None
    if request.user.is_authenticated:
        recent_calculations = get_recent_calculations(request.user)

    available_algorithms = []

    # Оплата за шаги — всегда
    available_algorithms.append({
        'title': 'Оплата за шаги',
        'description': 'Рассчитайте выплаты пользователям за пройденные километры. 1 км = 1 фунт (£).',
        'url': 'step_payment_calculator',
        'icon': 'fas fa-walking',
    })

    available_algorithms.append({
        'title': 'День рождения',
        'description': 'Начисление подарков за день рождения и участие в празднике.',
        'url': 'birthday_reward_calculator',
        'icon': 'fas fa-gift',
    })


    # Только для суперпользователей
    if request.user.is_superuser:
        print("DEBUG: Пользователь — суперпользователь, добавляем алгоритмы")  # ← Проверка в консоли
        available_algorithms.extend([
            {
                'title': 'Вычет денег',
                'description': 'Снимите средства с баланса пользователя вручную.',
                'url': 'money_deduction',
                'icon': 'fas fa-minus-circle',
            },
            
        ])
    else:
        print("DEBUG: Пользователь — НЕ суперпользователь")

    print(f"DEBUG: Всего алгоритмов: {len(available_algorithms)}")  # ← Сколько передаётся

    context = {
        'algorithms': available_algorithms,
        'recent_calculations': recent_calculations,
    }
    return render(request, 'algorithms.html', context)




def index(request):
    return render(request, 'index.html')


def events(request):
    """Страница событий"""
    return render(request, 'events.html')


def get_recent_calculations(user):
    """Возвращает последние 5 расчетов в зависимости от прав пользователя"""
    if user.is_superuser:
        return StepPaymentAlgorithm.objects.select_related('user', 'user__profile').all().order_by('-created_at')[:5]
    return StepPaymentAlgorithm.objects.select_related('user__profile').filter(user=user).order_by('-created_at')[:5]




@login_required
def step_payment_calculator(request):
    """Калькулятор оплаты за шаги"""
    amount_earned = None
    calculation = None
    form = StepPaymentForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        amount_earned = form.calculate_amount()
        calculation = form.save(request)
        if calculation:
            messages.success(
                request,
                f"Начислено {amount_earned}£ пользователю {calculation.user.get_full_name()}"
            )

    context = {
        'form': form,
        'amount_earned': amount_earned,
        'is_superuser': request.user.is_superuser,
    }
    return render(request, 'algorithms/step_payment.html', context)


@login_required
@user_passes_test(lambda u: u.is_superuser)
def money_deduction(request):
    """Вычет денег у пользователей (только для суперпользователей)"""
    form = MoneyDeductionForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        success, message = form.save(request)
        if success:
            messages.success(request, message)
            return redirect('transaction_history')
        else:
            messages.error(request, message)

    recent_deductions = MoneyDeductionLog.objects.select_related('user', 'deducted_by').all().order_by('-created_at')[:5]

    context = {
        'form': form,
        'recent_deductions': recent_deductions,
        'page_title': 'Вычет виртуальных денег',
    }
    return render(request, 'algorithms/money_deduction.html', context)


@login_required
@user_passes_test(lambda u: u.is_superuser)
def deduction_history(request):
    """История всех вычетов"""
    deductions = MoneyDeductionLog.objects.select_related('user', 'deducted_by').all().order_by('-created_at')
    context = {
        'deductions': deductions,
        'page_title': 'История вычетов',
    }
    return render(request, 'transactions/history.html', context)


@login_required
@user_passes_test(lambda u: u.is_superuser)
def balance_correction(request):
    """Коррекция баланса пользователя"""
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        correction_type = request.POST.get('correction_type')
        amount_str = request.POST.get('amount')
        reason = request.POST.get('reason', '').strip()

        if not all([user_id, correction_type, amount_str, reason]):
            messages.error(request, "Все поля обязательны.")
            return render(request, 'algorithms/balance_correction.html', {'users': User.objects.all()})

        try:
            user = User.objects.select_related('profile').get(id=user_id)
            amount = float(amount_str)

            if amount <= 0:
                messages.error(request, "Сумма должна быть положительной.")
                return redirect('balance_correction')

            profile = user.profile

            if correction_type == 'add':
                profile.add_money(amount=amount, reason=reason, transaction_type='correction')
                messages.success(request, f"Добавлено {amount}£ пользователю {user.get_full_name()}")
            elif correction_type == 'subtract':
                if profile.virtual_balance >= amount:
                    # Используем отрицательную сумму через существующую логику
                    profile.add_money(amount=-amount, reason=reason, transaction_type='deduction')
                    messages.success(request, f"Вычтено {amount}£ у пользователя {user.get_full_name()}")
                else:
                    messages.error(request, "Недостаточно средств на балансе")
            else:
                messages.error(request, "Некорректный тип коррекции.")
                return redirect('balance_correction')

            return redirect('user_transactions', user_id=user.id)

        except User.DoesNotExist:
            messages.error(request, "Пользователь не найден.")
        except (ValueError, Exception) as e:
            messages.error(request, f"Ошибка: {str(e)}")

    users = User.objects.select_related('profile').all().order_by('username')
    context = {
        'users': users,
        'page_title': 'Коррекция баланса',
    }
    return render(request, 'algorithms/balance_correction.html', context)


@login_required
@user_passes_test(lambda u: u.is_superuser)
def get_user_info(request, user_id):
    """API для получения информации о пользователе"""
    try:
        user = User.objects.select_related('profile').get(id=user_id)
        data = {
            'id': user.id,
            'username': user.username,
            'full_name': user.get_full_name() or user.username,
            'email': user.email,
            'balance': str(user.profile.virtual_balance),
            'total_earned': str(user.profile.total_earned),
            'total_deducted': str(user.profile.total_deducted),
            'steps_balance': user.profile.steps_balance,
        }
        return JsonResponse(data)
    except User.DoesNotExist:
        return JsonResponse({'error': 'Пользователь не найден'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@user_passes_test(lambda u: u.is_superuser)
def debug_balances(request):
    """Страница для отладки балансов"""
    users = User.objects.select_related('profile').all().order_by('username')
    context = {
        'users': users,
        'page_title': 'Отладка балансов',
    }
    return render(request, 'algorithms/debug_balances.html', context)


@login_required
@user_passes_test(lambda u: u.is_superuser)
def delete_deduction(request, deduction_id):
    """Удаление записи о вычете с возвратом средств"""
    deduction = get_object_or_404(MoneyDeductionLog, id=deduction_id)
    form = DeleteDeductionForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        reason = form.cleaned_data['reason']
        deduction.soft_delete(deleted_by=request.user, reason=reason)
        messages.success(
            request,
            f"Запись о вычете #{deduction_id} удалена. Деньги возвращены на баланс."
        )
        return redirect('deduction_history')

    context = {
        'form': form,
        'deduction': deduction,
        'page_title': 'Удаление записи о вычете',
    }
    return render(request, 'algorithms/delete_deduction.html', context)




@login_required
def birthday_reward_calculator(request):
    birthday_person = None
    main_form = BirthdayRewardForm(request.POST or None)
    guests_form = None
    attendees = None
    guest_fields = []  # ← Инициализируем пустым

    if request.method == 'POST':
        if 'select_birthday' in request.POST:
            if main_form.is_valid():
                birthday_person = main_form.cleaned_data['birthday_person']
                attendees = User.objects.exclude(
                    id=birthday_person.user.id
                ).exclude(
                    family_info__relationship='parent'
                ).select_related('family_info')
                guests_form = BirthdayGuestAttendanceForm(
                    attendees=attendees,
                    birthday_person=birthday_person
                )

                # ✅ Формируем guest_fields сразу после создания формы
                guest_fields = []
                if attendees:
                    for user in attendees:
                        field_name = f'attendance_{user.id}'
                        if field_name in guests_form.fields:
                            combo_field = None
                            try:
                                fm = user.family_info
                                if (fm.relationship == 'child' and fm.is_close_relative and
                                        birthday_person.relationship == 'parent'):
                                    combo_field_name = f'combo_years_{user.id}'
                                    if combo_field_name in guests_form.fields:
                                        combo_field = guests_form[combo_field_name]
                            except:
                                pass

                            guest_fields.append({
                                'user': user,
                                'field': guests_form[field_name],
                                'combo_field': combo_field,
                            })

        elif 'confirm_attendance' in request.POST:
            birthday_person_id = request.POST.get('birthday_person_id')
            try:
                birthday_person = FamilyMember.objects.get(id=birthday_person_id)
            except FamilyMember.DoesNotExist:
                messages.error(request, "Именинник не найден.")
                return redirect('birthday_reward_calculator')

            attendees = User.objects.exclude(
                id=birthday_person.user.id
            ).exclude(
                family_info__relationship='parent'
            ).select_related('family_info')

            if guests_form.is_valid():
                rewards = []
                with db_transaction.atomic():
                    # --- 1. Начисление имениннику ---
                    amount_to_birthday_person = 100

                    if birthday_person.relationship == 'child':
                        siblings_count = FamilyMember.objects.filter(
                            user__in=attendees,
                            relationship='sibling'
                        ).count() + FamilyMember.objects.filter(
                            user__in=attendees,
                            relationship='child'
                        ).count()
                        amount_to_birthday_person += 100 * siblings_count
                    elif birthday_person.relationship == 'parent':
                        amount_to_birthday_person = 0
                    else:
                        amount_to_birthday_person = 100

                    if amount_to_birthday_person > 0:
                        transaction = Transaction.objects.create(
                            user=birthday_person.user,
                            transaction_type='other',
                            amount=amount_to_birthday_person,
                            description="🎁 Подарок на день рождения",
                            reason=f"От {request.user.get_full_name()} — ДР {birthday_person.user.get_full_name()}",
                        )
                        rewards.append({
                            'user': birthday_person.user,
                            'amount': amount_to_birthday_person,
                            'reason': 'Именинник',
                            'transaction': transaction,
                        })

                    # --- 2. Начисление гостям ---
                    for guest in attendees:
                        attendance_type = guests_form.get_attendance_for_user(guest.id)
                        if attendance_type == 'absent':
                            continue

                        amount = 100
                        reason = "Участие в ДР"

                        try:
                            if (birthday_person.relationship == 'parent' and
                                    guest.family_info.relationship == 'child' and
                                    guest.family_info.is_close_relative):

                                combo_years = guests_form.get_combo_years_for_user(guest.id)
                                amount = 100 + 100 * combo_years
                                reason = f"Ребёнок на ДР родителя ({combo_years} лет комбо)"
                        except AttributeError:
                            pass  # family_info отсутствует

                        multiplier = 1.0 if attendance_type == 'in_person' else 0.5
                        final_amount = int(amount * multiplier)

                        if final_amount > 0:
                            transaction = Transaction.objects.create(
                                user=guest,
                                transaction_type='other',
                                amount=final_amount,
                                description=f"🎉 Участие в ДР {birthday_person.user.username}",
                                reason=reason,
                                status='pending',
                            )
                            rewards.append({
                                'user': guest,
                                'amount': final_amount,
                                'reason': reason,
                                'transaction': transaction,
                            })

                messages.success(request, "Награды за день рождения отправлены на подтверждение.")
                return render(request, 'algorithms/birthday_result.html', {
                    'rewards': rewards,
                    'birthday_person': birthday_person.user,
                    'pending': True,
                })
            else:
                print("DEBUG: Ошибки guests_form:", guests_form.errors)

                # ✅ Пересоздаём guest_fields после invalid form
                guest_fields = []
                if attendees:
                    for user in attendees:
                        field_name = f'attendance_{user.id}'
                        if field_name in guests_form.fields:
                            combo_field = None
                            try:
                                fm = user.family_info
                                if (fm.relationship == 'child' and fm.is_close_relative and
                                        birthday_person.relationship == 'parent'):
                                    combo_field_name = f'combo_years_{user.id}'
                                    if combo_field_name in guests_form.fields:
                                        combo_field = guests_form[combo_field_name]
                            except:
                                pass

                            guest_fields.append({
                                'user': user,
                                'field': guests_form[field_name],
                                'combo_field': combo_field,
                            })

    # ✅ Условие: только если был выбран именинник
    if not guests_form and birthday_person and request.method != 'POST':
        attendees = User.objects.exclude(
            id=birthday_person.user.id
        ).exclude(
            family_info__relationship='parent'
        ).select_related('family_info')
        guests_form = BirthdayGuestAttendanceForm(
            attendees=attendees,
            birthday_person=birthday_person
        )
        
        # ✅ И сразу формируем guest_fields
        guest_fields = []
        for user in attendees:
            field_name = f'attendance_{user.id}'
            if field_name in guests_form.fields:
                combo_field = None
                try:
                    fm = user.family_info
                    if (fm.relationship == 'child' and fm.is_close_relative and
                            birthday_person.relationship == 'parent'):
                        combo_field_name = f'combo_years_{user.id}'
                        if combo_field_name in guests_form.fields:
                            combo_field = guests_form[combo_field_name]
                except:
                    pass

                guest_fields.append({
                    'user': user,
                    'field': guests_form[field_name],
                    'combo_field': combo_field,
                })

    return render(request, 'algorithms/birthday_calculator.html', {
        'form': main_form,
        'attendees_form': guests_form,
        'birthday_person': birthday_person,
        'attendees': attendees,
        'guest_fields': guest_fields,
        'page_title': 'Алгоритм: День рождения',
    })




@login_required
@user_passes_test(lambda u: u.is_superuser)
def pending_transactions(request):
    """Страница транзакций, ожидающих подтверждения"""
    pending_tx = Transaction.objects.filter(status='pending', is_deleted=False).select_related('user', 'processed_by').order_by('created_at')
    return render(request, 'algorithms/pending_transactions.html', {
        'pending_tx': pending_tx,
        'page_title': 'Ожидающие транзакции',
    })


@login_required
@user_passes_test(lambda u: u.is_superuser)
def approve_transaction(request, tx_id):
    """Подтвердить транзакцию"""
    transaction = get_object_or_404(Transaction, id=tx_id, status='pending')
    success = transaction.approve(processed_by=request.user)
    if success:
        messages.success(request, f"Транзакция #{tx_id} одобрена. {transaction.amount}£ зачислено {transaction.user.get_full_name()}.")
    else:
        messages.error(request, "Не удалось подтвердить транзакцию.")
    return redirect('pending_transactions')


@login_required
@user_passes_test(lambda u: u.is_superuser)
def reject_transaction(request, tx_id):
    """Отклонить транзакцию"""
    transaction = get_object_or_404(Transaction, id=tx_id, status='pending')
    reason = request.POST.get('reason', 'Без указания причины')
    success = transaction.reject(processed_by=request.user, reason=reason)
    if success:
        messages.success(request, f"Транзакция #{tx_id} отклонена.")
    else:
        messages.error(request, "Не удалось отклонить транзакцию.")
    return redirect('pending_transactions')


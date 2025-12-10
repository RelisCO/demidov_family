from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.db.models import Sum, F, Q
from .forms import StepPaymentForm, MoneyDeductionForm, DeletePaymentForm, DeleteDeductionForm
from .models import StepPaymentAlgorithm, MoneyDeductionLog, PaymentDeletionLog


def index(request):
    return render(request, 'index.html')

def algorithms(request):
    """Главная страница алгоритмов"""
    # Получаем последние расчеты для текущего пользователя
    recent_calculations = None
    if request.user.is_authenticated:
        if request.user.is_superuser:
            # Для суперпользователя показываем все расчеты
            recent_calculations = StepPaymentAlgorithm.objects.all().order_by('-created_at')[:5]
        else:
            # Для обычных пользователей только свои расчеты
            recent_calculations = StepPaymentAlgorithm.objects.filter(
                user=request.user
            ).order_by('-created_at')[:5]
    
    context = {
        'recent_calculations': recent_calculations,
    }
    return render(request, 'algorithms.html', context)

@login_required
def step_payment_calculator(request):
    """Калькулятор оплаты за шаги"""
    amount_earned = None
    calculation = None
    form = StepPaymentForm(request.POST or None)
    
    if request.method == 'POST' and form.is_valid():
        # Рассчитываем сумму
        amount_earned = form.calculate_amount()
        
        # Сохраняем расчет
        calculation = form.save(request)
        
        if calculation:
            messages.success(
                request, 
                f"Начислено {amount_earned}£ пользователю {calculation.user.get_full_name()}"
            )
    
    context = {
        'form': form,
        'amount_earned': amount_earned,
        'is_superuser': request.user.is_superuser if request.user.is_authenticated else False,
    }
    return render(request, 'algorithms/step_payment.html', context)


def events(request):
    return render(request, 'events.html')

@login_required
@user_passes_test(lambda u: u.is_superuser)
def money_deduction(request):
    """Вычет денег у пользователей (только для суперпользователей)"""
    form = MoneyDeductionForm(request.POST or None)
    
    if request.method == 'POST' and form.is_valid():
        success, message = form.save(request)
        
        if success:
            messages.success(request, message)
            return redirect('deduction_history')
        else:
            messages.error(request, message)
    
    # Получаем последние 5 вычетов для отображения
    recent_deductions = MoneyDeductionLog.objects.all().order_by('-created_at')[:5]
    
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
    deductions = MoneyDeductionLog.objects.all().order_by('-created_at')
    
    context = {
        'deductions': deductions,
        'page_title': 'История вычетов',
    }
    return render(request, 'algorithms/deduction_history.html', context)


@login_required
@user_passes_test(lambda u: u.is_superuser)
def balance_correction(request):
    """Коррекция баланса пользователя"""
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        correction_type = request.POST.get('correction_type')
        amount = request.POST.get('amount')
        reason = request.POST.get('reason')
        
        try:
            user = User.objects.get(id=user_id)
            amount = float(amount)
            
            if correction_type == 'add':
                user.profile.add_money(
                    amount=amount,
                    reason=reason,
                    transaction_type='correction'
                )
                messages.success(request, f"Добавлено {amount}£ пользователю {user.get_full_name()}")
            elif correction_type == 'subtract':
                if user.profile.virtual_balance >= amount:
                    user.profile.add_money(
                        amount=amount,
                        reason=reason,
                        transaction_type='deduction'
                    )
                    messages.success(request, f"Вычтено {amount}£ у пользователя {user.get_full_name()}")
                else:
                    messages.error(request, "Недостаточно средств на балансе")
            
            return redirect('user_transactions', user_id=user_id)
            
        except (User.DoesNotExist, ValueError) as e:
            messages.error(request, f"Ошибка: {str(e)}")
    
    users = User.objects.all()
    context = {
        'users': users,
        'page_title': 'Коррекция баланса',
    }
    return render(request, 'algorithms/balance_correction.html', context)


from django.http import JsonResponse

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
        return JsonResponse({'error': 'User not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
@user_passes_test(lambda u: u.is_superuser)
def debug_balances(request):
    """Страница для отладки балансов"""
    users = User.objects.select_related('profile').all()
    
    context = {
        'users': users,
        'page_title': 'Отладка балансов',
    }
    return render(request, 'algorithms/debug_balances.html', context)

def events(request):
    return render(request, 'events.html')

@login_required
@user_passes_test(lambda u: u.is_superuser)
def delete_deduction(request, deduction_id):
    """Удаление записи о вычете"""
    deduction = get_object_or_404(MoneyDeductionLog, id=deduction_id)
    
    if request.method == 'POST':
        form = DeleteDeductionForm(request.POST)
        if form.is_valid():
            reason = form.cleaned_data['reason']
            
            # Мягкое удаление с возвратом денег
            deduction.soft_delete(request.user, reason)
            
            messages.success(request, 
                f"Запись о вычете #{deduction_id} удалена. "
                f"Деньги возвращены на баланс пользователя."
            )
            
            return redirect('deduction_history')
    else:
        form = DeleteDeductionForm()
    
    context = {
        'form': form,
        'deduction': deduction,
        'page_title': 'Удаление записи о вычете',
    }
    return render(request, 'algorithms/delete_deduction.html', context)


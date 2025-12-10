# apps/transactions/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.db.models import Sum, Count, Q, F
from django.core.paginator import Paginator
from .models import Transaction, TransactionDeletionLog

@login_required
@user_passes_test(lambda u: u.is_superuser)
def clear_transaction_history(request):
    """Очистить историю транзакций - простое удаление"""
    if request.method == 'POST':
        # Удаляем все транзакции
        count = Transaction.objects.all().count()
        Transaction.objects.all().delete()
        
        messages.success(request, f"История транзакций очищена. Удалено записей: {count}")
        return redirect('transaction_history')
    
    # Если GET запрос, просто редиректим на историю
    return redirect('transaction_history')


@login_required
@user_passes_test(lambda u: u.is_superuser)
def transaction_history(request):
    """История всех транзакций"""
    # Фильтры
    status = request.GET.get('status', '')
    transaction_type = request.GET.get('type', '')
    
    # Все транзакции
    transactions = Transaction.objects.all().order_by('-created_at')
    
    # Применяем фильтры
    if status:
        transactions = transactions.filter(status=status)
    if transaction_type:
        transactions = transactions.filter(transaction_type=transaction_type)
    
    # Статистика
    stats = {
        'total': transactions.count(),
        'pending': transactions.filter(status='pending').count(),
        'approved': transactions.filter(status='approved').count(),
        'rejected': transactions.filter(status='rejected').count(),
        'total_amount': transactions.filter(status='approved').aggregate(
            total=Sum('amount')
        )['total'] or 0,
    }
    
    context = {
        'transactions': transactions,
        'stats': stats,
        'current_status': status,
        'current_type': transaction_type,
        'statuses': Transaction.STATUS_CHOICES,
        'types': Transaction.TRANSACTION_TYPES,
        'page_title': 'История транзакций',
    }
    return render(request, 'transactions/history.html', context)

@login_required
@user_passes_test(lambda u: u.is_superuser)
def approve_transaction(request, transaction_id):
    """Подтвердить транзакцию"""
    transaction = get_object_or_404(Transaction, id=transaction_id)
    
    if transaction.status == 'pending':
        if transaction.approve(request.user):
            messages.success(request, f"Транзакция #{transaction_id} подтверждена")
        else:
            messages.error(request, f"Ошибка при подтверждении транзакции #{transaction_id}")
    else:
        messages.warning(request, f"Транзакция #{transaction_id} уже обработана")
    
    return redirect('transaction_history')

@login_required
@user_passes_test(lambda u: u.is_superuser)
def reject_transaction(request, transaction_id):
    """Отклонить транзакцию"""
    transaction = get_object_or_404(Transaction, id=transaction_id)
    
    if transaction.status == 'pending':
        reason = request.POST.get('reason', 'Транзакция отклонена')
        if transaction.reject(request.user, reason):
            messages.success(request, f"Транзакция #{transaction_id} отклонена")
        else:
            messages.error(request, f"Ошибка при отклонении транзакции #{transaction_id}")
    else:
        messages.warning(request, f"Транзакция #{transaction_id} уже обработана")
    
    return redirect('transaction_history')




@login_required
@user_passes_test(lambda u: u.is_superuser)
def transaction_detail(request, transaction_id):
    """Детальная информация о транзакции"""
    if request.user.is_superuser:
        transaction = get_object_or_404(Transaction, id=transaction_id, is_deleted=False)
    else:
        transaction = get_object_or_404(Transaction, id=transaction_id, user=request.user, is_deleted=False)
    
    context = {
        'transaction': transaction,
        'page_title': f'Транзакция #{transaction.id}',
    }
    return render(request, 'transactions/detail.html', context)

@login_required
@user_passes_test(lambda u: u.is_superuser)
def process_transaction(request, transaction_id):
    """Обработать транзакцию (для суперпользователя)"""
    transaction = get_object_or_404(Transaction, id=transaction_id, is_deleted=False)
    
    if transaction.status == 'pending':
        if transaction.process(request.user):
            messages.success(request, f"Транзакция #{transaction_id} успешно обработана")
        else:
            messages.error(request, f"Ошибка при обработке транзакции #{transaction_id}")
    else:
        messages.warning(request, f"Транзакция #{transaction_id} уже обработана")
    
    return redirect('transaction_history')

@login_required
@user_passes_test(lambda u: u.is_superuser)
def cancel_transaction(request, transaction_id):
    """Отменить транзакцию"""
    transaction = get_object_or_404(Transaction, id=transaction_id, is_deleted=False)
    
    if request.method == 'POST':
        reason = request.POST.get('reason', '')
        
        if transaction.cancel(request.user, reason):
            messages.success(request, f"Транзакция #{transaction_id} отменена")
        else:
            messages.error(request, f"Не удалось отменить транзакцию #{transaction_id}")
    
    return redirect('transaction_history')

@login_required
@user_passes_test(lambda u: u.is_superuser)
def delete_transaction(request, transaction_id):
    """Удалить транзакцию"""
    transaction = get_object_or_404(Transaction, id=transaction_id, is_deleted=False)
    
    if request.method == 'POST':
        reason = request.POST.get('reason', '')
        transaction.soft_delete(request.user, reason)
        messages.success(request, f"Транзакция #{transaction_id} удалена")
        return redirect('transaction_history')
    
    context = {
        'transaction': transaction,
        'page_title': 'Удаление транзакции',
    }
    return render(request, 'transactions/delete.html', context)

@login_required
@user_passes_test(lambda u: u.is_superuser)
def view_deleted_transactions(request):
    """Просмотр удаленных транзакций"""
    deleted_transactions = Transaction.objects.filter(is_deleted=True).order_by('-created_at')
    
    context = {
        'deleted_transactions': deleted_transactions,
        'page_title': 'Корзина транзакций',
    }
    return render(request, 'transactions/deleted.html', context)

@login_required
@user_passes_test(lambda u: u.is_superuser)
def restore_transaction(request, transaction_id):
    """Восстановить удаленную транзакцию"""
    transaction = get_object_or_404(Transaction, id=transaction_id, is_deleted=True)
    
    transaction.is_deleted = False
    transaction.save()
    
    messages.success(request, f"Транзакция #{transaction_id} восстановлена")
    return redirect('view_deleted_transactions')

@login_required
@user_passes_test(lambda u: u.is_superuser)
def user_transaction_report(request, user_id):
    """Отчет по транзакциям пользователя"""
    user = get_object_or_404(User, id=user_id)
    
    # Все транзакции пользователя
    transactions = Transaction.objects.filter(user=user, is_deleted=False)
    
    # Статистика
    stats = transactions.aggregate(
        total_count=Count('id'),
        total_amount=Sum('amount'),
        completed_amount=Sum('amount', filter=Q(status='completed')),
        pending_count=Count('id', filter=Q(status='pending')),
    )
    
    # По типам транзакций
    by_type = transactions.values('transaction_type').annotate(
        count=Count('id'),
        total=Sum('amount'),
        avg=Sum('amount') / Count('id')
    )
    
    # По месяцам
    from django.db.models.functions import TruncMonth
    by_month = transactions.annotate(
        month=TruncMonth('created_at')
    ).values('month').annotate(
        count=Count('id'),
        total=Sum('amount')
    ).order_by('-month')
    
    context = {
        'user': user,
        'transactions': transactions.order_by('-created_at')[:50],
        'stats': stats,
        'by_type': by_type,
        'by_month': by_month,
        'page_title': f'Отчет по транзакциям: {user.get_full_name()}',
    }
    return render(request, 'transactions/user_report.html', context)


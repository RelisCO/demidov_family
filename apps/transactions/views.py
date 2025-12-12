# apps/transactions/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.db.models import Sum, Count, Q, F
from django.core.paginator import Paginator
from django.db import transaction as db_transaction
from .models import Transaction, TransactionDeletionLog

# --- Улучшение 1: Рефакторинг повторяющихся проверок и логирования ---
def _log_and_message(request, action, transaction_id, success=True, extra=None):
    """Вспомогательная функция для логирования действий и отправки сообщений."""
    if success:
        messages.success(request, extra or f"Транзакция #{transaction_id} успешно {action}.")
    else:
        messages.error(request, extra or f"Ошибка при {action} транзакции #{transaction_id}.")

# --- Улучшение 2: Защита от массового удаления и логирование при очистке истории ---
@login_required
@user_passes_test(lambda u: u.is_superuser)
@login_required
@user_passes_test(lambda u: u.is_superuser)
def clear_transaction_history(request):
    """Очистка истории транзакций с логированием удалённых записей."""
    if request.method == 'POST':
        with db_transaction.atomic():
            transactions = Transaction.objects.filter(is_deleted=False)
            count = transactions.count()

            # Используем метод soft_delete() каждой транзакции — он сам запишет original_data
            for trans in transactions:
                trans.soft_delete(
                    deleted_by=request.user,
                    reason="Очистка всей истории администратором"
                )

            messages.success(request, f"История транзакций очищена. Удалено записей: {count}")
        return redirect('transaction_history')
    return redirect('transaction_history')


# --- Улучшение 3: Оптимизация запросов и фильтрации в истории транзакций ---
@login_required
@user_passes_test(lambda u: u.is_superuser)
def transaction_history(request):
    """История всех транзакций с оптимизированными запросами."""
    status = request.GET.get('status', '')
    transaction_type = request.GET.get('type', '')

    # Используем select_related для уменьшения количества запросов
    transactions = Transaction.objects.select_related('user').filter(is_deleted=False).order_by('-created_at')

    if status:
        transactions = transactions.filter(status=status)
    if transaction_type:
        transactions = transactions.filter(transaction_type=transaction_type)

    # Пагинация
    paginator = Paginator(transactions, 50)  # 50 записей на странице
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Оптимизированная статистика
    stats = (
        transactions.aggregate(
            total=Count('id'),
            pending=Count('id', filter=Q(status='pending')),
            approved=Count('id', filter=Q(status='approved')),
            rejected=Count('id', filter=Q(status='rejected')),
            total_amount=Sum('amount', filter=Q(status='approved'))
        )
    )
    stats['total_amount'] = stats['total_amount'] or 0

    context = {
        'transactions': page_obj,  # Передаём объект пагинатора
        'stats': stats,
        'current_status': status,
        'current_type': transaction_type,
        'statuses': Transaction.STATUS_CHOICES,
        'types': Transaction.TRANSACTION_TYPES,
        'page_title': 'История транзакций',
    }
    return render(request, 'transactions/history.html', context)

# --- Улучшение 4: Объединение approve и reject в одну логику с проверкой ---
@login_required
@user_passes_test(lambda u: u.is_superuser)
def approve_transaction(request, transaction_id):
    """Подтвердить транзакцию с логированием результата."""
    transaction = get_object_or_404(Transaction, id=transaction_id, is_deleted=False)

    if transaction.status != 'pending':
        messages.warning(request, f"Транзакция #{transaction_id} уже обработана.")
        return redirect('transaction_history')

    success = transaction.approve(request.user)
    _log_and_message(request, "подтверждена", transaction_id, success)
    return redirect('transaction_history')

@login_required
@user_passes_test(lambda u: u.is_superuser)
def reject_transaction(request, transaction_id):
    """Отклонить транзакцию с указанием причины."""
    transaction = get_object_or_404(Transaction, id=transaction_id, is_deleted=False)

    if transaction.status != 'pending':
        messages.warning(request, f"Транзакция #{transaction_id} уже обработана.")
        return redirect('transaction_history')

    reason = request.POST.get('reason', 'Отклонено без указания причины')
    success = transaction.reject(request.user, reason)
    _log_and_message(request, "отклонена", transaction_id, success)
    return redirect('transaction_history')

# --- Улучшение 5: Удаление дублирования и лишней проверки в detail ---
@login_required
@user_passes_test(lambda u: u.is_superuser)
def transaction_detail(request, transaction_id):
    """Детали транзакции — доступ только для суперпользователей."""
    transaction = get_object_or_404(Transaction, id=transaction_id, is_deleted=False)
    context = {
        'transaction': transaction,
        'page_title': f'Транзакция #{transaction.id}',
    }
    return render(request, 'transactions/detail.html', context)

# --- Улучшение 6: Проверка статуса и результата процессинга ---
@login_required
@user_passes_test(lambda u: u.is_superuser)
def process_transaction(request, transaction_id):
    """Обработка транзакции (апрув + бизнес-логика)."""
    transaction = get_object_or_404(Transaction, id=transaction_id, is_deleted=False)

    if transaction.status != 'pending':
        messages.warning(request, f"Транзакция #{transaction_id} уже обработана.")
        return redirect('transaction_history')

    success = transaction.process(request.user)
    _log_and_message(request, "обработана", transaction_id, success)
    return redirect('transaction_history')

# --- Улучшение 7: Отмена с проверкой метода и reason ---
@login_required
@user_passes_test(lambda u: u.is_superuser)
def cancel_transaction(request, transaction_id):
    """Отмена транзакции только по POST."""
    transaction = get_object_or_404(Transaction, id=transaction_id, is_deleted=False)

    if request.method == 'POST':
        reason = request.POST.get('reason', 'Без указания причины')
        success = transaction.cancel(request.user, reason)
        _log_and_message(request, "отменена", transaction_id, success)
    return redirect('transaction_history')

# --- Улучшение 8: Удаление с подтверждением и логированием ---
@login_required
@user_passes_test(lambda u: u.is_superuser)
def delete_transaction(request, transaction_id):
    """Удаление транзакции с подтверждением и логированием."""
    transaction = get_object_or_404(Transaction, id=transaction_id, is_deleted=False)

    if request.method == 'POST':
        reason = request.POST.get('reason', 'Без причины')
        transaction.soft_delete(request.user, reason)
        messages.success(request, f"Транзакция #{transaction_id} удалена.")
        return redirect('transaction_history')

    context = {
        'transaction': transaction,
        'page_title': 'Удаление транзакции',
    }
    return render(request, 'transactions/delete.html', context)

# --- Улучшение 9: Просмотр удалённых с пагинацией ---
@login_required
@user_passes_test(lambda u: u.is_superuser)
def view_deleted_transactions(request):
    """Просмотр удалённых транзакций с пагинацией."""
    deleted_transactions = Transaction.objects.filter(is_deleted=True).select_related('user').order_by('-created_at')

    paginator = Paginator(deleted_transactions, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'deleted_transactions': page_obj,
        'page_title': 'Корзина транзакций',
    }
    return render(request, 'transactions/deleted.html', context)

# --- Улучшение 10: Восстановление с логикой ---
@login_required
@user_passes_test(lambda u: u.is_superuser)
def restore_transaction(request, transaction_id):
    """Восстановление удалённой транзакции."""
    transaction = get_object_or_404(Transaction, id=transaction_id, is_deleted=True)
    transaction.is_deleted = False
    transaction.save()
    messages.success(request, f"Транзакция #{transaction_id} восстановлена.")
    return redirect('view_deleted_transactions')

# --- Улучшение 11: Отчёт пользователя — оптимизация агрегаций ---
@login_required
@user_passes_test(lambda u: u.is_superuser)
def user_transaction_report(request, user_id):
    """Отчёт по транзакциям пользователя с оптимизированными агрегациями."""
    user = get_object_or_404(User, id=user_id)
    transactions = Transaction.objects.filter(user=user, is_deleted=False).select_related('user')

    # Статистика
    stats = transactions.aggregate(
        total_count=Count('id'),
        total_amount=Sum('amount'),
        completed_amount=Sum('amount', filter=Q(status='completed')),
        pending_count=Count('id', filter=Q(status='pending')),
    )
    stats['total_amount'] = stats['total_amount'] or 0
    stats['completed_amount'] = stats['completed_amount'] or 0

    # По типам
    by_type = transactions.values('transaction_type').annotate(
        count=Count('id'),
        total=Sum('amount'),
        avg=Sum('amount') / Count('id')
    ).order_by('-total')

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

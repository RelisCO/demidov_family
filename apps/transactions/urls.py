# apps/transactions/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # Основные операции с транзакциями
    path('', views.transaction_history, name='transaction_history'),
    path('clear/', views.clear_transaction_history, name='clear_transaction_history'),
    path('deleted/', views.view_deleted_transactions, name='view_deleted_transactions'),
    path('<int:transaction_id>/restore/', views.restore_transaction, name='restore_transaction'),

    # Детали и отчеты
    path('<int:transaction_id>/', views.transaction_detail, name='transaction_detail'),
    path('user/<int:user_id>/report/', views.user_transaction_report, name='user_transaction_report'),

    # Управление транзакциями (группировка по действиям)
    path('<int:transaction_id>/approve/', views.approve_transaction, name='approve_transaction'),
    path('<int:transaction_id>/reject/', views.reject_transaction, name='reject_transaction'),
    path('<int:transaction_id>/process/', views.process_transaction, name='process_transaction'),
    path('<int:transaction_id>/cancel/', views.cancel_transaction, name='cancel_transaction'),
    path('<int:transaction_id>/delete/', views.delete_transaction, name='delete_transaction'),
]

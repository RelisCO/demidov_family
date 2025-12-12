from django.urls import path
from . import views


urlpatterns = [
    # Основные страницы
    path('', views.index, name='index'),
    path('algorithms/', views.algorithms, name='algorithms'),
    path('step-payment/', views.step_payment_calculator, name='step_payment_calculator'),
    path('events/', views.events, name='events'),
    path('birthday-reward/', views.birthday_reward_calculator, name='birthday_reward_calculator'),
    path('pending-transactions/', views.pending_transactions, name='pending_transactions'),
    path('approve-transaction/<int:tx_id>/', views.approve_transaction, name='approve_transaction'),
    path('reject-transaction/<int:tx_id>/', views.reject_transaction, name='reject_transaction'),

    # Управление вычетами
    path('money-deduction/', views.money_deduction, name='money_deduction'),
    # API
    path('api/user-info/<int:user_id>/', views.get_user_info, name='get_user_info'),

    # Отладка
    path('debug-balances/', views.debug_balances, name='debug_balances'),
]

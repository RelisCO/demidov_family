from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('algorithms/', views.algorithms, name='algorithms'),
    path('step-payment/', views.step_payment_calculator, name='step_payment_calculator'),
    
    # Вычеты денег
    path('money-deduction/', views.money_deduction, name='money_deduction'),
    path('deduction-history/', views.deduction_history, name='deduction_history'),
    path('delete-deduction/<int:deduction_id>/', views.delete_deduction, name='delete_deduction'),
    
    # API
    path('api/user-info/<int:user_id>/', views.get_user_info, name='get_user_info'),
    
    # Отладка
    path('debug-balances/', views.debug_balances, name='debug_balances'),
    
    path('events/', views.events, name='events'),
]
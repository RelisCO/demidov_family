from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from apps.users import views as user_views
from django.conf import settings
from django.conf.urls.static import static
from apps.algorithms import views
from django.views.generic import TemplateView



urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('apps.algorithms.urls')),
    path('algorithms/', views.algorithms, name='algorithms'),
    path('events/', views.events, name='events'),
    path('users/', include('apps.users.urls')),
    path('transactions/', include('apps.transactions.urls')),
    
    path('login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(template_name='logout.html'), name='logout'),
    
    # Статические страницы
    path('logged-out/', TemplateView.as_view(template_name='logged_out.html'), name='logged_out'),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
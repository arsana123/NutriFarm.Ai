from django.contrib.auth import views as auth_views
from django.urls import path

from . import views
from .forms import FarmerLoginForm

app_name = 'testing'

urlpatterns = [
    # Public pages
    path('about/', views.about, name='about'),
    path('features/', views.features, name='features'),
    path('contact/', views.contact, name='contact'),
    # Accounts
    path('register/', views.register, name='register'),
    path(
        'login/',
        auth_views.LoginView.as_view(
            template_name='testing/login.html',
            authentication_form=FarmerLoginForm,
            redirect_authenticated_user=True,
        ),
        name='login',
    ),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    # Farmer area
    path('dashboard/', views.dashboard, name='dashboard'),
    path('samples/', views.sample_history, name='sample_history'),
    path('samples/submit/', views.sample_create, name='sample_create'),
    path('samples/export.csv', views.sample_export_csv, name='sample_export_csv'),
    path('sample/<int:sample_id>/', views.sample_detail, name='sample_detail'),
    path('sample/<int:sample_id>/edit/', views.sample_update, name='sample_update'),
    path('sample/<int:sample_id>/delete/', views.sample_delete, name='sample_delete'),
    path('sample/<int:sample_id>/evaluate/', views.evaluate_sample, name='evaluate_sample'),
    path('sample/<int:sample_id>/result/', views.sample_result, name='sample_result'),
]

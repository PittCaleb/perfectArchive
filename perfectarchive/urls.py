from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views

urlpatterns = [
    # Obscured admin URL
    path('perfect/perfect-admin/', admin.site.urls),

    # Include urls from our 'archives' app
    path('', include('archives.urls')),

    # Obscured login/logout URLs
    path('perfect/login/', auth_views.LoginView.as_view(), name='login'),
    path('perfect/logout/', auth_views.LogoutView.as_view(), name='logout'),
    # You can add other auth URLs here if needed (password reset, etc.)
]


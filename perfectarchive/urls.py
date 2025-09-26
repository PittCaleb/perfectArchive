from django.contrib import admin
from django.urls import path, include
from django.views.generic.base import TemplateView

urlpatterns = [
    path('perfect/perfect-admin/', admin.site.urls),

    # THIS IS THE FIX: We've added the namespace='gameplay' argument.
    path('play/', include('gameplay.urls', namespace='gameplay')),

    # Include urls from our 'archives' app
    path('', include('archives.urls')),

    # Include Django's built-in authentication urls
    path('perfect/', include('django.contrib.auth.urls')),

    path("robots.txt", TemplateView.as_view(template_name="robots.txt", content_type="text/plain")),
    path("ads.txt", TemplateView.as_view(template_name="ads.txt", content_type="text/plain")),
]


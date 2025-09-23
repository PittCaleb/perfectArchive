from django.contrib import admin
from django.urls import path, include
from django.views.generic.base import TemplateView

urlpatterns = [
    path('perfect/perfect-admin/', admin.site.urls),
    # Include urls from our 'archives' app
    path('', include('archives.urls')),
    # Include Django's built-in authentication urls (for login/logout)
    path('perfect/', include('django.contrib.auth.urls')),

    # Serve the robots.txt file
    path("robots.txt", TemplateView.as_view(template_name="robots.txt", content_type="text/plain")),

    # Add this new line to serve the ads.txt file
    path("ads.txt", TemplateView.as_view(template_name="ads.txt", content_type="text/plain")),
]


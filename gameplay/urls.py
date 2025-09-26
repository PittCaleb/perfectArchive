from django.urls import path
from . import views

app_name = 'gameplay'

urlpatterns = [
    # This is the root of the 'play' section, e.g., /play/
    path('', views.play_view, name='play'),

    # NEW: Route for the preliminary round game
    path('prelim/', views.prelim_game_view, name='prelim_game'),
]


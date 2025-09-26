from django.urls import path
from . import views

app_name = 'gameplay'

urlpatterns = [
    # This is the root of the 'play' section, e.g., /play/
    path('', views.play_view, name='play'),

    # Route for the preliminary round game
    path('prelim/', views.prelim_game_view, name='prelim_game'),

    # API route for saving scores
    path('api/save_score/', views.save_score_api, name='save_score_api'),

    # API route for fetching leaderboards
    path('api/get_leaderboard/', views.get_leaderboard_api, name='get_leaderboard_api'),
]


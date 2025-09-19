from django.urls import path
from . import views

urlpatterns = [
    # Homepage
    path('', views.index, name='index'),

    # Main pages
    path('recent-games/', views.recent_games_view, name='recent_games'),
    path('statistics/', views.statistics_view, name='statistics'),
    path('show-info/', views.show_info_view, name='show_info'),
    path('about/', views.about_view, name='about'),

    # Score a game page (for logged-in scorekeepers)
    path('score-game/', views.score_game_view, name='score_game'),

    # API endpoint to receive game data
    path('game_entry', views.game_entry_api, name='game_entry_api'),
]


from django.urls import path
from . import views

urlpatterns = [
    # Homepage
    path('', views.index, name='index'),

    # Main pages
    path('recent-games/', views.recent_games_view, name='recent_games'),
    path('statistics/', views.statistics_view, name='statistics'),
    path('analysis/', views.analysis_view, name='analysis'),
    path('show-info/', views.show_info_view, name='show_info'),
    path('about/', views.about_view, name='about'),

    # Permalink route for individual games
    path('game/<int:game_id>/', views.game_permalink_view, name='game_permalink'),

    # Admin-only pages
    path('score-game/', views.score_game_view, name='score_game'),
    path('add-line/', views.add_preliminary_line_view, name='add_line'),

    # API endpoint
    path('game_entry', views.game_entry_api, name='game_entry_api'),
]


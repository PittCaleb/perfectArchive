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
    path('search/', views.search_games_view, name='search_games'),  # <--- New line
    path('about/', views.about_view, name='about'),

    # Permalink route for individual games
    path('game/<int:game_id>/', views.game_permalink_view, name='game_permalink'),

    # Admin-only pages
    path('game-admin/', views.game_admin_view, name='game_admin'),
    path('score-game/', views.score_game_view, name='score_game'),
    path('add-line/', views.add_preliminary_line_view, name='add_line'),
    path('add-fast-line/', views.add_fast_line_view, name='add_fast_line'),
    path('add-final-line/', views.add_final_line_view, name='add_final_line'),
    path('manage-leaderboards/', views.manage_leaderboards_view, name='manage_leaderboards'),

    # API endpoint
    path('game_entry', views.game_entry_api, name='game_entry_api'),


]


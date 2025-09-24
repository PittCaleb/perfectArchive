from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required, permission_required
from .models import Game, Player, CustomUser, Syndication, StatisticsCache
import json
from django.core.paginator import Paginator
from django.db.models import Count, Avg, Q, Sum, F
from collections import defaultdict
from .stats_utils import update_statistics_cache, _calculate_game_outcomes


# Home page view
def index(request):
    latest_game = Game.objects.prefetch_related('players').order_by('-air_date', '-episode_number').first()
    if latest_game:
        advancing_ids, winner_ids = _calculate_game_outcomes(latest_game)
        for p in latest_game.players.all():
            p.is_advancing = p.id in advancing_ids
            p.is_winner = p.id in winner_ids
            # Add calculated fields for template display
            p.round_total_score = p.round1_score + p.round2_score + p.round3_score + p.round4_score
            p.fast_line_total_score = p.round_total_score + (p.fast_line_score or 0)

    top_champions = Player.objects.filter(total_winnings__gt=1000).select_related('game').order_by('-total_winnings')[
                    :3]

    context = {
        'latest_game': latest_game,
        'top_champions': top_champions,
    }
    return render(request, 'archives/index.html', context)


# View for the "Score a Game" page
@login_required
@permission_required('archives.add_game', raise_exception=True)
def score_game_view(request):
    return render(request, 'archives/score_game.html')


# View for the Recent Games page
def recent_games_view(request):
    game_list = Game.objects.prefetch_related('players').order_by('-air_date', '-episode_number')

    for game in game_list:
        advancing_ids, winner_ids = _calculate_game_outcomes(game)
        for p in game.players.all():
            p.is_advancing = p.id in advancing_ids
            p.is_winner = p.id in winner_ids
            p.round_total_score = p.round1_score + p.round2_score + p.round3_score + p.round4_score
            p.fast_line_total_score = p.round_total_score + (p.fast_line_score or 0)

    paginator = Paginator(game_list, 5)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'archives/recent_games.html', {'page_obj': page_obj})


# View for Show Info page
def show_info_view(request):
    stations = Syndication.objects.all().order_by('state', 'city')
    syndication_data = defaultdict(list)
    for station in stations:
        syndication_data[station.state].append({
            "city": station.city,
            "station": station.station,
            "time": station.time
        })

    context = {
        'states': sorted(syndication_data.keys()),
        'syndication_data_json': json.dumps(syndication_data)
    }
    return render(request, 'archives/show_info.html', context)


# View for Statistics page
def statistics_view(request):
    """
    Retrieves pre-calculated statistics from the cache for fast rendering.
    """
    cached_stats = StatisticsCache.objects.order_by('-updated_at').first()
    context = {}

    if cached_stats:
        context = cached_stats.data

        latest_game_id = context.get('latest_game_id')
        if latest_game_id:
            context['latest_game'] = Game.objects.get(id=latest_game_id)

        def rehydrate_players(player_data_list):
            if not player_data_list: return []

            player_ids = [p_data.get('id') for p_data in player_data_list if p_data.get('id')]
            if not player_ids: return []

            players_dict = {p.id: p for p in Player.objects.filter(id__in=player_ids).select_related('game')}

            rehydrated_list = []
            for p_data in player_data_list:
                player_id = p_data.get('id')
                player_obj = players_dict.get(player_id)
                if player_obj:
                    player_obj.fast_line_total = p_data.get('fast_line_total')
                    player_obj.round_total = p_data.get('round_total')
                    player_obj.page_number = p_data.get('page_number')
                    rehydrated_list.append(player_obj)
            return rehydrated_list

        context['top_fast_line_players'] = rehydrate_players(context.get('top_fast_line_players', []))
        context['top_fast_line_scores'] = rehydrate_players(context.get('top_fast_line_scores', []))
        context['leaderboard_data'] = rehydrate_players(context.get('leaderboard_data', []))

        for podium_lb in context.get('podium_leaderboards', []):
            podium_lb['players'] = rehydrate_players(podium_lb.get('players', []))

        # Efficiently re-hydrate comeback players
        comeback_player_data = [c.get('player', {}) for c in context.get('top_comebacks', [])]
        rehydrated_comeback_players = rehydrate_players(comeback_player_data)
        rehydrated_players_dict = {p.id: p for p in rehydrated_comeback_players}

        for comeback in context.get('top_comebacks', []):
            player_id = comeback.get('player', {}).get('id')
            if player_id in rehydrated_players_dict:
                comeback['player'] = rehydrated_players_dict[player_id]

    return render(request, 'archives/statistics.html', context)


# View for Analysis page
def analysis_view(request):
    return render(request, 'archives/analysis.html')


# View for About page
def about_view(request):
    return render(request, 'archives/about.html')


# API Endpoint
@csrf_exempt
@login_required
@permission_required('archives.add_game', raise_exception=True)
def game_entry_api(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            from django.db import transaction
            with transaction.atomic():
                game = Game.objects.create(
                    submitted_by=request.user,
                    episode_title=data.get('episodeTitle'),
                    air_date=data.get('airDate'),
                    episode_number=data.get('episodeNumber'),
                    fast_line_tiebreaker_winner_podium=data.get('fastLineTiebreakerWinnerId')
                )
                for player_data in data.get('players', []):
                    scores = player_data.get('scores', {})
                    Player.objects.create(
                        game=game, name=player_data.get('name'), podium_number=player_data.get('podium'),
                        round1_correct=player_data.get('round1Correct'),
                        round2_correct=player_data.get('round2Correct'),
                        round3_correct=player_data.get('round3Correct'),
                        round4_correct=player_data.get('round4Correct'),
                        round1_score=scores.get('round1Score', 0), round2_score=scores.get('round2Score', 0),
                        round3_score=scores.get('round3Score', 0), round4_score=scores.get('round4Score', 0),
                        won_tiebreaker=(data.get('roundTiebreakerWinnerId') == player_data.get('podium')),
                        fast_line_correct_count=player_data.get('fastLineCorrect'),
                        fast_line_incorrect_count=player_data.get('fastLineIncorrect'),
                        fast_line_score=scores.get('fastLineScore'),
                        final_round_correct_count=player_data.get('finalRoundCorrect'),
                        total_winnings=scores.get('finalTotal', 0)
                    )

            # After successfully saving, trigger the cache update
            update_statistics_cache()

            return JsonResponse({'message': 'Game data saved successfully!'}, status=201)
        except json.JSONDecodeError:
            return JsonResponse({'message': 'Invalid JSON format.'}, status=400)
        except Exception as e:
            print(f"Error saving game data: {e}")
            return JsonResponse({'message': 'An internal error occurred.'}, status=500)
    return JsonResponse({'message': 'Only POST method is allowed.'}, status=405)


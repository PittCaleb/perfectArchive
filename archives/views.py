from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required, permission_required, user_passes_test
from .models import Game, Player, CustomUser, Syndication, StatisticsCache, PreliminaryLine
import json
from django.core.paginator import Paginator
from django.db.models import Count, Avg, Q, Sum, F
from collections import defaultdict
from .stats_utils import update_statistics_cache
from .forms import PreliminaryLineForm
from django.urls import reverse
from django.contrib import messages


def _calculate_game_outcomes(game):
    """
    Helper function to determine advancing players and winners for a given game.
    This avoids duplicating logic across multiple views.
    """
    players = list(game.players.all())
    if not players:
        return [], []

    for p in players:
        p.round_total = p.round1_score + p.round2_score + p.round3_score + p.round4_score

    players.sort(key=lambda p: p.round_total, reverse=True)

    # Determine advancing players from round 1-4
    advancing_ids = []
    if len(players) > 0 and players[0].round_total >= 0:
        advancing_ids.append(players[0].id)

    tiebreaker_winner = next((p for p in players if p.won_tiebreaker), None)
    if tiebreaker_winner:
        if tiebreaker_winner.id not in advancing_ids:
            advancing_ids.append(tiebreaker_winner.id)
    elif len(players) > 1 and players[1].round_total >= 0:
        if players[1].id not in advancing_ids:
            advancing_ids.append(players[1].id)

    # Determine the final winner(s)
    winner_ids = []
    advancing_players = [p for p in players if p.id in advancing_ids]

    # Check for a fast line tie-breaker first
    if game.fast_line_tiebreaker_winner_podium is not None:
        winner_player = next(
            (p for p in advancing_players if p.podium_number == game.fast_line_tiebreaker_winner_podium), None)
        if winner_player:
            winner_ids.append(winner_player.id)
    else:
        # If no tie-breaker, determine winner by highest score
        max_fast_line_total = -1
        for p in advancing_players:
            p.fast_line_total = p.round_total + (p.fast_line_score or 0)
            if p.fast_line_total > max_fast_line_total:
                max_fast_line_total = p.fast_line_total

        if max_fast_line_total >= 0:
            winner_ids = [p.id for p in advancing_players if p.fast_line_total == max_fast_line_total]

    return advancing_ids, winner_ids


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


# View for Permalink Redirection
def game_permalink_view(request, game_id):
    all_game_ids = list(Game.objects.values_list('id', flat=True).order_by('-air_date', '-episode_number'))

    try:
        index = all_game_ids.index(game_id)
        page_number = (index // 5) + 1

        redirect_url = f"{reverse('recent_games')}?page={page_number}#game-{game_id}"
        return redirect(redirect_url)
    except ValueError:
        return redirect('recent_games')


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

        # Re-hydrating comebacks requires the player object for the link
        for comeback in context.get('top_comebacks', []):
            player_data = comeback.get('player', {})
            player_id = player_data.get('id')
            if player_id:
                comeback['player'] = Player.objects.get(id=player_id)

    return render(request, 'archives/statistics.html', context)


# View for Analysis page
def analysis_view(request):
    return render(request, 'archives/analysis.html')


# View for About page
def about_view(request):
    return render(request, 'archives/about.html')


# Helper function and view for the new Beta Test page
def is_beta_tester(user):
    return user.is_authenticated and user.role == CustomUser.Role.BETA_TESTER

def is_beta_tester_or_superuser(user):
    return user.is_authenticated and (user.role == CustomUser.Role.BETA_TESTER or user.is_superuser)

@user_passes_test(is_beta_tester_or_superuser)
def play_view(request):
    return render(request, 'archives/play.html')


@login_required
@permission_required('archives.add_game', raise_exception=True)
def add_preliminary_line_view(request):
    if request.method == 'POST':
        form = PreliminaryLineForm(request.POST)
        if form.is_valid():
            instance = form.save()
            messages.success(request,
                             f"Successfully added line for Game {instance.game.id}, Round {instance.round_number}.")

            # Smart redirect logic
            next_game_id = instance.game.id
            next_round_number = instance.round_number + 1
            if instance.round_number == 4:
                next_game_id += 1
                next_round_number = 1

            redirect_url = f"{reverse('add_line')}?game={next_game_id}&round_number={next_round_number}"
            return redirect(redirect_url)
    else:
        initial_data = {
            'game': request.GET.get('game'),
            'round_number': request.GET.get('round_number')
        }
        form = PreliminaryLineForm(initial=initial_data)

    # If no initial data is provided via GET, determine the next logical entry
    if not request.GET.get('game'):
        last_line = PreliminaryLine.objects.order_by('-game__id', '-round_number').first()
        if last_line:
            next_game = last_line.game
            next_round = last_line.round_number + 1
            if next_round > 4:
                next_round = 1
                # Find the next game ID in sequence
                next_game_obj = Game.objects.filter(id__gt=next_game.id).order_by('id').first()
                if next_game_obj:
                    next_game = next_game_obj
                else:  # Or just increment if there's a gap
                    next_game = Game.objects.get(id=next_game.id + 1)

            form.initial['game'] = next_game
            form.initial['round_number'] = next_round
        else:
            # First ever entry, default to first game
            first_game = Game.objects.order_by('id').first()
            if first_game:
                form.initial['game'] = first_game
                form.initial['round_number'] = 1

    return render(request, 'archives/add_preliminary_line.html', {'form': form})


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


from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required, permission_required
from .models import Game, Player, CustomUser, Syndication
import json
from django.core.paginator import Paginator
from django.db.models import Count, Avg, Q, Sum, F
from collections import defaultdict


# Home page view
def index(request):
    """
    Fetches data for the homepage, including the most recent game and top champions.
    """
    # Fetch the most recent game, prefetching players to avoid extra queries
    latest_game = Game.objects.prefetch_related('players').order_by('-id').first()

    if latest_game:
        # We need to calculate advancement and winner status for the template
        players = list(latest_game.players.all())
        for p in players:
            p.round_total = p.round1_score + p.round2_score + p.round3_score + p.round4_score

        players.sort(key=lambda p: p.round_total, reverse=True)

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

        max_fast_line_total = -1
        advancing_players = [p for p in players if p.id in advancing_ids]
        for p in advancing_players:
            p.fast_line_total = p.round_total + (p.fast_line_score or 0)
            if p.fast_line_total > max_fast_line_total:
                max_fast_line_total = p.fast_line_total

        if max_fast_line_total >= 0:
            winner_ids = [p.id for p in advancing_players if p.fast_line_total == max_fast_line_total]
        else:
            winner_ids = []

        # Attach the calculated properties to the players on the latest_game object
        for p in latest_game.players.all():
            p.is_advancing = p.id in advancing_ids
            p.is_winner = p.id in winner_ids
            p.round_total_score = p.round1_score + p.round2_score + p.round3_score + p.round4_score
            p.fast_line_total_score = p.round_total_score + (p.fast_line_score or 0)

    # Fetch top 3 champions based on total winnings
    top_champions = Player.objects.select_related('game').order_by('-total_winnings')[:3]

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
        players = list(game.players.all())

        for p in players:
            p.round_total = p.round1_score + p.round2_score + p.round3_score + p.round4_score

        players.sort(key=lambda p: p.round_total, reverse=True)

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

        max_fast_line_total = -1

        advancing_players = [p for p in players if p.id in advancing_ids]
        for p in advancing_players:
            p.fast_line_total = p.round_total + (p.fast_line_score or 0)
            if p.fast_line_total > max_fast_line_total:
                max_fast_line_total = p.fast_line_total

        if max_fast_line_total >= 0:
            winner_ids = [p.id for p in advancing_players if p.fast_line_total == max_fast_line_total]
        else:
            winner_ids = []

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
    latest_game = Game.objects.order_by('-id').first()

    # --- Podium Performance Logic ---
    podium_stats = []
    total_players_by_podium = Player.objects.values('podium_number').annotate(total=Count('id'))
    total_map = {item['podium_number']: item['total'] for item in total_players_by_podium}

    for i in range(1, 5):
        total_players = total_map.get(i, 0)
        if total_players == 0:
            podium_stats.append({
                'podium': i, 'round1_pct': 0, 'round2_pct': 0, 'round3_pct': 0, 'round4_pct': 0, 'avg_correct': 0
            })
            continue

        stats = Player.objects.filter(podium_number=i).aggregate(
            r1_correct=Count('id', filter=Q(round1_correct=True)),
            r2_correct=Count('id', filter=Q(round2_correct=True)),
            r3_correct=Count('id', filter=Q(round3_correct=True)),
            r4_correct=Count('id', filter=Q(round4_correct=True)),
        )

        total_correct = stats['r1_correct'] + stats['r2_correct'] + stats['r3_correct'] + stats['r4_correct']
        avg_correct = (total_correct / total_players) if total_players > 0 else 0

        podium_stats.append({
            'podium': i,
            'round1_pct': (stats['r1_correct'] / total_players) * 100,
            'round2_pct': (stats['r2_correct'] / total_players) * 100,
            'round3_pct': (stats['r3_correct'] / total_players) * 100,
            'round4_pct': (stats['r4_correct'] / total_players) * 100,
            'avg_correct': avg_correct
        })

    if podium_stats and any(s['avg_correct'] > 0 for s in podium_stats):
        keys_to_color = ['round1_pct', 'round2_pct', 'round3_pct', 'round4_pct', 'avg_correct']
        for key in keys_to_color:
            values = [s[key] for s in podium_stats]
            if not values: continue
            min_val, max_val = min(values), max(values)
            if min_val == max_val:
                for stat in podium_stats: stat[key + '_color'] = 'yellow'
                continue
            for stat in podium_stats:
                if stat[key] == max_val:
                    stat[key + '_color'] = 'green'
                elif stat[key] == min_val:
                    stat[key + '_color'] = 'red'
                else:
                    stat[key + '_color'] = 'yellow'
    else:
        for stat in podium_stats:
            for key in ['round1_pct', 'round2_pct', 'round3_pct', 'round4_pct', 'avg_correct']:
                stat[key + '_color'] = 'gray'

    # --- Advancement Stats Logic ---
    advancement_stats_raw = {i: {'total': 0, 'advanced': 0, 'won': 0} for i in range(1, 5)}
    all_games = Game.objects.prefetch_related('players').all()

    for game in all_games:
        players = list(game.players.all())
        if not players: continue
        for p in players: p.round_total = p.round1_score + p.round2_score + p.round3_score + p.round4_score
        players.sort(key=lambda p: p.round_total, reverse=True)
        advancing_ids = []
        if len(players) > 0 and players[0].round_total >= 0: advancing_ids.append(players[0].id)
        tiebreaker_winner = next((p for p in players if p.won_tiebreaker), None)
        if tiebreaker_winner:
            if tiebreaker_winner.id not in advancing_ids: advancing_ids.append(tiebreaker_winner.id)
        elif len(players) > 1 and players[1].round_total >= 0:
            if players[1].id not in advancing_ids: advancing_ids.append(players[1].id)
        max_fast_line_total = -1
        advancing_players = [p for p in players if p.id in advancing_ids]
        for p in advancing_players:
            p.fast_line_total = p.round_total + (p.fast_line_score or 0)
            if p.fast_line_total > max_fast_line_total: max_fast_line_total = p.fast_line_total
        winner_ids = [p.id for p in advancing_players if
                      p.fast_line_total == max_fast_line_total] if max_fast_line_total >= 0 else []
        for p in game.players.all():
            podium = p.podium_number
            advancement_stats_raw[podium]['total'] += 1
            if p.id in advancing_ids: advancement_stats_raw[podium]['advanced'] += 1
            if p.id in winner_ids: advancement_stats_raw[podium]['won'] += 1

    avg_scores_by_podium = Player.objects.annotate(
        round_total=F('round1_score') + F('round2_score') + F('round3_score') + F('round4_score')
    ).values('podium_number').annotate(
        avg_score=Avg('round_total')
    )
    avg_score_map = {item['podium_number']: item['avg_score'] for item in avg_scores_by_podium}

    advancement_stats = []
    for podium, data in advancement_stats_raw.items():
        total = data['total']
        advancement_stats.append({
            'podium': podium, 'advanced_count': data['advanced'],
            'advanced_pct': (data['advanced'] / total * 100) if total > 0 else 0,
            'won_count': data['won'], 'won_pct': (data['won'] / total * 100) if total > 0 else 0,
            'avg_score': avg_score_map.get(podium, 0) or 0
        })

    if advancement_stats:
        for key in ['avg_score', 'advanced_pct', 'won_pct']:
            values = [s[key] for s in advancement_stats]
            if not values: continue
            min_val, max_val = min(values), max(values)
            if min_val == max_val:
                for stat in advancement_stats: stat[key + '_color'] = 'yellow'
                continue
            for stat in advancement_stats:
                if stat[key] == max_val:
                    stat[key + '_color'] = 'green'
                elif stat[key] == min_val:
                    stat[key + '_color'] = 'red'
                else:
                    stat[key + '_color'] = 'yellow'

    # --- Fast Line Performance & Leaderboard Logic ---
    correct_counts = dict(
        Player.objects.filter(fast_line_correct_count__isnull=False).values_list('fast_line_correct_count').annotate(
            count=Count('id')))
    incorrect_counts = dict(Player.objects.filter(fast_line_incorrect_count__isnull=False).values_list(
        'fast_line_incorrect_count').annotate(count=Count('id')))
    chart_labels = list(range(16))
    correct_data = [correct_counts.get(i, 0) for i in range(16)]
    incorrect_data = [incorrect_counts.get(i, 0) for i in range(16)]
    avg_stats = Player.objects.aggregate(avg_correct=Avg('fast_line_correct_count'),
                                         avg_incorrect=Avg('fast_line_incorrect_count'))
    top_fast_line_players = Player.objects.filter(fast_line_correct_count__isnull=False).order_by(
        '-fast_line_correct_count', 'fast_line_incorrect_count')[:5]
    top_fast_line_scores = Player.objects.annotate(
        round_total=Sum(F('round1_score') + F('round2_score') + F('round3_score') + F('round4_score'))).annotate(
        fast_line_total=F('round_total') + F('fast_line_score')).filter(fast_line_score__isnull=False).select_related(
        'game').order_by('-fast_line_total')[:10]
    leaderboard_data = Player.objects.select_related('game').order_by('-total_winnings')[:10]

    # --- Final Round Performance Logic ---
    final_round_counts = dict(Player.objects.filter(final_round_correct_count__isnull=False).values_list(
        'final_round_correct_count').annotate(count=Count('id')))
    total_final_round_players = sum(final_round_counts.values())
    final_round_stats = []
    for i in range(6):
        count = final_round_counts.get(i, 0)
        final_round_stats.append({
            'correct_count': i,
            'count': count,
            'pct': (count / total_final_round_players * 100) if total_final_round_players > 0 else 0
        })

    if final_round_stats and total_final_round_players > 0:
        values = [s['pct'] for s in final_round_stats]
        min_val, max_val = min(values), max(values)
        if min_val == max_val:
            for stat in final_round_stats: stat['pct_color'] = 'yellow'
        else:
            for stat in final_round_stats:
                if stat['pct'] == max_val:
                    stat['pct_color'] = 'green'
                elif stat['pct'] == min_val:
                    stat['pct_color'] = 'red'
                else:
                    stat['pct_color'] = 'yellow'

    context = {
        'latest_game': latest_game,
        'podium_stats': podium_stats,
        'advancement_stats': advancement_stats,
        'chart_labels': json.dumps(chart_labels),
        'correct_data': json.dumps(correct_data),
        'incorrect_data': json.dumps(incorrect_data),
        'avg_stats': avg_stats,
        'top_fast_line_players': top_fast_line_players,
        'final_round_stats': final_round_stats,
        'top_fast_line_scores': top_fast_line_scores,
        'leaderboard_data': leaderboard_data
    }
    return render(request, 'archives/statistics.html', context)


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
                game = Game.objects.create(submitted_by=request.user, episode_title=data.get('episodeTitle'),
                                           air_date=data.get('airDate'), episode_number=data.get('episodeNumber'))
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
                        won_tiebreaker=(data.get('tiebreakerWinnerId') == player_data.get('podium')),
                        fast_line_correct_count=player_data.get('fastLineCorrect'),
                        fast_line_incorrect_count=player_data.get('fastLineIncorrect'),
                        fast_line_score=scores.get('fastLineScore'),
                        final_round_correct_count=player_data.get('finalRoundCorrect'),
                        total_winnings=scores.get('finalTotal', 0)
                    )
            return JsonResponse({'message': 'Game data saved successfully!'}, status=201)
        except json.JSONDecodeError:
            return JsonResponse({'message': 'Invalid JSON format.'}, status=400)
        except Exception as e:
            print(f"Error saving game data: {e}")
            return JsonResponse({'message': 'An internal error occurred.'}, status=500)
    return JsonResponse({'message': 'Only POST method is allowed.'}, status=405)


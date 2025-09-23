from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required, permission_required
from .models import Game, Player, CustomUser, Syndication
import json
from django.core.paginator import Paginator
from django.db.models import Count, Avg, Q, Sum, F
from collections import defaultdict


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

    # --- Turn Order Performance Logic ---
    turn_stats = {i: {'attempts': 0, 'correct': 0} for i in range(1, 5)}
    all_players = Player.objects.all()
    all_games = Game.objects.prefetch_related('players').all()
    all_games_count = all_games.count()

    turn_order_map = {
        1: {1: 1, 2: 2, 3: 3, 4: 4},
        2: {1: 4, 2: 1, 3: 2, 4: 3},
        3: {1: 3, 2: 4, 3: 1, 4: 2},
        4: {1: 2, 2: 3, 3: 4, 4: 1},
    }

    for player in all_players:
        podium = player.podium_number
        round_results = [player.round1_correct, player.round2_correct, player.round3_correct, player.round4_correct]

        for i, is_correct in enumerate(round_results):
            round_num = i + 1
            if is_correct is not None:
                turn = turn_order_map[round_num][podium]
                turn_stats[turn]['attempts'] += 1
                if is_correct:
                    turn_stats[turn]['correct'] += 1

    turn_performance = []
    for turn, data in turn_stats.items():
        turn_performance.append({
            'turn': turn,
            'pct': (data['correct'] / data['attempts'] * 100) if data['attempts'] > 0 else 0
        })

    # --- Preliminary Round Winner Distribution Logic ---
    prelim_dist_counts = {i: 0 for i in range(5)}
    total_prelim_rounds = 0
    come_from_behind_victories = []
    total_fast_line_games = 0

    for game in all_games:
        players = list(game.players.all())
        if not players: continue

        # Calculate prelim distribution
        for i in range(1, 5):
            round_correct_field = f'round{i}_correct'
            was_played = any(getattr(p, round_correct_field) is not None for p in players)
            if was_played:
                correct_count = sum(1 for p in players if getattr(p, round_correct_field) is True)
                prelim_dist_counts[correct_count] += 1
                total_prelim_rounds += 1

        # Calculate Come From Behind stats
        advancing_ids, winner_ids = _calculate_game_outcomes(game)
        advancing_players = [p for p in players if p.id in advancing_ids]
        if len(advancing_players) == 2:
            total_fast_line_games += 1
            p1 = advancing_players[0]
            p2 = advancing_players[1]
            p1.round_total = p1.round1_score + p1.round2_score + p1.round3_score + p1.round4_score
            p2.round_total = p2.round1_score + p2.round2_score + p2.round3_score + p2.round4_score

            leader = p1 if p1.round_total > p2.round_total else p2
            trailer = p2 if p1.round_total > p2.round_total else p1

            if leader != trailer and trailer.id in winner_ids:
                score_diff = leader.round_total - trailer.round_total
                come_from_behind_victories.append(score_diff)

    preliminary_round_dist = []
    for i in range(5):
        count = prelim_dist_counts.get(i, 0)
        preliminary_round_dist.append({
            'correct_count': i,
            'count': count,
            'pct': (count / total_prelim_rounds * 100) if total_prelim_rounds > 0 else 0
        })

    if preliminary_round_dist and total_prelim_rounds > 0:
        values = [s['pct'] for s in preliminary_round_dist]
        min_val, max_val = min(values), max(values)
        if min_val == max_val:
            for stat in preliminary_round_dist: stat['pct_color'] = 'yellow'
        else:
            for stat in preliminary_round_dist:
                if stat['pct'] == max_val:
                    stat['pct_color'] = 'green'
                elif stat['pct'] == min_val:
                    stat['pct_color'] = 'red'
                else:
                    stat['pct_color'] = 'yellow'

    # --- Come From Behind Stats ---
    come_from_behind_stats = {
        'count': len(come_from_behind_victories),
        'pct': (len(come_from_behind_victories) / total_fast_line_games * 100) if total_fast_line_games > 0 else 0,
        'avg_diff': sum(come_from_behind_victories) / len(
            come_from_behind_victories) if come_from_behind_victories else 0,
        'max_diff': max(come_from_behind_victories) if come_from_behind_victories else 0
    }

    # --- Podium Performance Logic ---
    podium_stats_query = Player.objects.values('podium_number').annotate(
        total_players=Count('id'),
        r1_correct=Count('id', filter=Q(round1_correct=True)),
        r2_correct=Count('id', filter=Q(round2_correct=True)),
        r3_correct=Count('id', filter=Q(round3_correct=True)),
        r4_correct=Count('id', filter=Q(round4_correct=True))
    ).order_by('podium_number')

    podium_stats = []
    for i in range(1, 5):
        data = next((item for item in podium_stats_query if item['podium_number'] == i), None)
        if not data or data['total_players'] == 0:
            podium_stats.append(
                {'podium': i, 'round1_pct': 0, 'round2_pct': 0, 'round3_pct': 0, 'round4_pct': 0, 'avg_correct': 0})
            continue

        total_players = data['total_players']
        total_correct = data['r1_correct'] + data['r2_correct'] + data['r3_correct'] + data['r4_correct']
        avg_correct = (total_correct / total_players) if total_players > 0 else 0

        podium_stats.append({
            'podium': i,
            'round1_pct': (data['r1_correct'] / total_players) * 100,
            'round2_pct': (data['r2_correct'] / total_players) * 100,
            'round3_pct': (data['r3_correct'] / total_players) * 100,
            'round4_pct': (data['r4_correct'] / total_players) * 100,
            'avg_correct': avg_correct
        })

    if podium_stats:
        keys_to_color = ['round1_pct', 'round2_pct', 'round3_pct', 'round4_pct', 'avg_correct']
        for key in keys_to_color:
            values = [s[key] for s in podium_stats]
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

    # --- Aggregate Podium Performance Logic ---
    aggregate_stats = None
    if all_games_count > 0:
        total_r1_correct = sum(s['r1_correct'] for s in podium_stats_query)
        total_r2_correct = sum(s['r2_correct'] for s in podium_stats_query)
        total_r3_correct = sum(s['r3_correct'] for s in podium_stats_query)
        total_r4_correct = sum(s['r4_correct'] for s in podium_stats_query)
        total_correct_answers = total_r1_correct + total_r2_correct + total_r3_correct + total_r4_correct

        aggregate_stats = {
            'avg_r1': total_r1_correct / all_games_count,
            'avg_r2': total_r2_correct / all_games_count,
            'avg_r3': total_r3_correct / all_games_count,
            'avg_r4': total_r4_correct / all_games_count,
            'avg_total': total_correct_answers / all_games_count
        }

    # --- Advancement Stats Logic ---
    advancement_stats_raw = {i: {'total': 0, 'advanced': 0, 'won': 0} for i in range(1, 5)}

    for game in all_games:
        advancing_ids, winner_ids = _calculate_game_outcomes(game)
        for p in game.players.all():
            podium = p.podium_number
            advancement_stats_raw[podium]['total'] += 1
            if p.id in advancing_ids: advancement_stats_raw[podium]['advanced'] += 1
            if p.id in winner_ids: advancement_stats_raw[podium]['won'] += 1

    avg_scores_by_podium = Player.objects.annotate(
        round_total=F('round1_score') + F('round2_score') + F('round3_score') + F('round4_score')
    ).values('podium_number').annotate(avg_score=Avg('round_total'))
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
        for key in ['avg_score', 'won_pct']:
            values = [s[key] for s in advancement_stats]
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

        sorted_by_adv_pct = sorted(advancement_stats, key=lambda x: x['advanced_pct'], reverse=True)
        if len(sorted_by_adv_pct) == 4:
            podium_color_map = {
                sorted_by_adv_pct[0]['podium']: 'green',
                sorted_by_adv_pct[1]['podium']: 'green',
                sorted_by_adv_pct[2]['podium']: 'red',
                sorted_by_adv_pct[3]['podium']: 'red',
            }
            for stat in advancement_stats:
                stat['advanced_pct_color'] = podium_color_map.get(stat['podium'], 'gray')

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
    top_fast_line_players = Player.objects.select_related('game').filter(
        fast_line_correct_count__isnull=False).order_by('-fast_line_correct_count', 'fast_line_incorrect_count')[:5]
    top_fast_line_scores = Player.objects.annotate(
        round_total=Sum(F('round1_score') + F('round2_score') + F('round3_score') + F('round4_score'))).annotate(
        fast_line_total=F('round_total') + (F('fast_line_score') or 0)).filter(
        fast_line_score__isnull=False).select_related('game').order_by('-fast_line_total')[:20]
    leaderboard_data = Player.objects.annotate(
        round_total=Sum(F('round1_score') + F('round2_score') + F('round3_score') + F('round4_score'))
    ).annotate(
        fast_line_total=F('round_total') + (F('fast_line_score') or 0)
    ).select_related('game').order_by('-total_winnings', '-fast_line_total')[:20]

    all_game_ids = list(Game.objects.values_list('id', flat=True).order_by('-air_date', '-episode_number'))

    leaderboard_players = list(top_fast_line_players) + list(top_fast_line_scores) + list(leaderboard_data)
    game_ids_to_map = {p.game_id for p in leaderboard_players}
    game_page_map = {game_id: (all_game_ids.index(game_id) // 5) + 1 for game_id in game_ids_to_map if
                     game_id in all_game_ids}
    for p in leaderboard_players:
        p.page_number = game_page_map.get(p.game_id)

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

    # --- Top Podium Scores Logic ---
    podium_leaderboards = []
    for i in range(1, 5):
        top_players = Player.objects.filter(podium_number=i).annotate(
            round_total=Sum(F('round1_score') + F('round2_score') + F('round3_score') + F('round4_score'))
        ).select_related('game').order_by('-round_total')[:10]

        for p in top_players:
            p.page_number = game_page_map.get(p.game_id)

        podium_leaderboards.append({
            'podium_number': i,
            'players': top_players
        })

    context = {
        'latest_game': latest_game,
        'podium_stats': podium_stats,
        'advancement_stats': advancement_stats,
        'turn_performance': turn_performance,
        'preliminary_round_dist': preliminary_round_dist,
        'chart_labels': json.dumps(chart_labels),
        'correct_data': json.dumps(correct_data),
        'incorrect_data': json.dumps(incorrect_data),
        'avg_stats': avg_stats,
        'top_fast_line_players': top_fast_line_players,
        'final_round_stats': final_round_stats,
        'top_fast_line_scores': top_fast_line_scores,
        'leaderboard_data': leaderboard_data,
        'podium_leaderboards': podium_leaderboards,
        'aggregate_stats': aggregate_stats,
        'come_from_behind_stats': come_from_behind_stats,
    }
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
            return JsonResponse({'message': 'Game data saved successfully!'}, status=201)
        except json.JSONDecodeError:
            return JsonResponse({'message': 'Invalid JSON format.'}, status=400)
        except Exception as e:
            print(f"Error saving game data: {e}")
            return JsonResponse({'message': 'An internal error occurred.'}, status=500)
    return JsonResponse({'message': 'Only POST method is allowed.'}, status=405)


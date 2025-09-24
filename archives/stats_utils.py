from .models import Game, Player, StatisticsCache
from django.db.models import Count, Avg, Q, Sum, F
from collections import defaultdict
import json


def _calculate_game_outcomes(game):
    """
    Helper function to determine advancing players and winners for a given game.
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

    winner_ids = []
    advancing_players = [p for p in players if p.id in advancing_ids]

    if game.fast_line_tiebreaker_winner_podium is not None:
        winner_player = next(
            (p for p in advancing_players if p.podium_number == game.fast_line_tiebreaker_winner_podium), None)
        if winner_player:
            winner_ids.append(winner_player.id)
    else:
        max_fast_line_total = -1
        for p in advancing_players:
            p.fast_line_total = p.round_total + (p.fast_line_score or 0)
            if p.fast_line_total > max_fast_line_total:
                max_fast_line_total = p.fast_line_total

        if max_fast_line_total >= 0:
            winner_ids = [p.id for p in advancing_players if p.fast_line_total == max_fast_line_total]

    return advancing_ids, winner_ids


def update_statistics_cache():
    """
    Performs all statistics calculations and saves the result to the cache.
    """
    latest_game = Game.objects.order_by('-id').first()
    if not latest_game:
        StatisticsCache.objects.all().delete()
        return

    all_players = Player.objects.select_related('game').all()
    all_games = Game.objects.prefetch_related('players').all()
    all_games_count = all_games.count()

    # --- Turn Order Performance Logic ---
    turn_stats = {i: {'attempts': 0, 'correct': 0} for i in range(1, 5)}
    turn_order_map = {
        1: {1: 1, 2: 2, 3: 3, 4: 4}, 2: {1: 4, 2: 1, 3: 2, 4: 3},
        3: {1: 3, 2: 4, 3: 1, 4: 2}, 4: {1: 2, 2: 3, 3: 4, 4: 1},
    }
    for player in all_players:
        podium = player.podium_number
        round_results = [player.round1_correct, player.round2_correct, player.round3_correct, player.round4_correct]
        for i, is_correct in enumerate(round_results):
            if is_correct is not None:
                turn = turn_order_map[i + 1][podium]
                turn_stats[turn]['attempts'] += 1
                if is_correct: turn_stats[turn]['correct'] += 1
    turn_performance = [{'turn': t, 'pct': (d['correct'] / d['attempts'] * 100) if d['attempts'] > 0 else 0} for t, d in
                        turn_stats.items()]

    # --- Distribution & Comeback Logic ---
    prelim_dist_counts = {i: 0 for i in range(5)}
    player_prelim_correct_counts = {i: 0 for i in range(5)}
    player_advancement_by_correct_count = {i: {'advanced': 0, 'total': 0} for i in range(5)}
    total_prelim_rounds = 0
    come_from_behind_victories = []
    total_fast_line_games = 0
    for game in all_games:
        players = list(game.players.all())
        if not players: continue
        advancing_ids, winner_ids = _calculate_game_outcomes(game)
        for p in players:
            correct_total = sum(
                1 for r in [p.round1_correct, p.round2_correct, p.round3_correct, p.round4_correct] if r is True)
            player_prelim_correct_counts[correct_total] += 1
            player_advancement_by_correct_count[correct_total]['total'] += 1
            if p.id in advancing_ids: player_advancement_by_correct_count[correct_total]['advanced'] += 1
        for i in range(1, 5):
            round_correct_field = f'round{i}_correct'
            if any(getattr(p, round_correct_field) is not None for p in players):
                correct_count = sum(1 for p in players if getattr(p, round_correct_field) is True)
                prelim_dist_counts[correct_count] += 1
                total_prelim_rounds += 1
        advancing_players = [p for p in players if p.id in advancing_ids]
        if len(advancing_players) == 2:
            total_fast_line_games += 1
            p1, p2 = advancing_players[0], advancing_players[1]
            p1.round_total = p1.round1_score + p1.round2_score + p1.round3_score + p1.round4_score
            p2.round_total = p2.round1_score + p2.round2_score + p2.round3_score + p2.round4_score
            leader = p1 if p1.round_total > p2.round_total else p2
            trailer = p2 if p1.round_total > p2.round_total else p1
            if leader != trailer and trailer.id in winner_ids:
                come_from_behind_victories.append({'player': trailer, 'diff': leader.round_total - trailer.round_total})

    def color_code_dist(dist_list):
        if not dist_list or not any(
            s.get('count', 0) > 0 or s.get('total', 0) > 0 or s.get('total_players', 0) > 0 for s in dist_list): return
        values = [s['pct'] for s in dist_list]
        min_val, max_val = min(values), max(values)
        if min_val == max_val:
            for stat in dist_list: stat['pct_color'] = 'yellow'
        else:
            for stat in dist_list:
                if stat['pct'] == max_val:
                    stat['pct_color'] = 'green'
                elif stat['pct'] == min_val:
                    stat['pct_color'] = 'red'
                else:
                    stat['pct_color'] = 'yellow'

    all_players_count = all_players.count()
    player_prelim_dist = [
        {'correct_count': i, 'count': c, 'pct': (c / all_players_count * 100) if all_players_count > 0 else 0} for i, c
        in player_prelim_correct_counts.items()]
    color_code_dist(player_prelim_dist)
    player_advancement_dist = [{'correct_count': i, 'advanced_count': d['advanced'], 'total_players': d['total'],
                                'pct': (d['advanced'] / d['total'] * 100) if d['total'] > 0 else 0} for i, d in
                               player_advancement_by_correct_count.items()]
    color_code_dist(player_advancement_dist)
    preliminary_round_dist = [
        {'correct_count': i, 'count': c, 'pct': (c / total_prelim_rounds * 100) if total_prelim_rounds > 0 else 0} for
        i, c in prelim_dist_counts.items()]
    color_code_dist(preliminary_round_dist)

    # --- Come From Behind Stats ---
    top_comebacks = sorted(come_from_behind_victories, key=lambda x: x['diff'], reverse=True)[:5]
    come_from_behind_stats = {
        'count': len(come_from_behind_victories),
        'pct': (len(come_from_behind_victories) / total_fast_line_games * 100) if total_fast_line_games > 0 else 0,
        'avg_diff': sum(v['diff'] for v in come_from_behind_victories) / len(
            come_from_behind_victories) if come_from_behind_victories else 0,
        'max_diff': max(v['diff'] for v in come_from_behind_victories) if come_from_behind_victories else 0
    }

    # --- Podium Performance ---
    podium_stats_query = Player.objects.values('podium_number').annotate(total_players=Count('id'),
                                                                         r1_correct=Count('id', filter=Q(
                                                                             round1_correct=True)),
                                                                         r2_correct=Count('id', filter=Q(
                                                                             round2_correct=True)),
                                                                         r3_correct=Count('id', filter=Q(
                                                                             round3_correct=True)),
                                                                         r4_correct=Count('id', filter=Q(
                                                                             round4_correct=True))).order_by(
        'podium_number')
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
        round_total=F('round1_score') + F('round2_score') + F('round3_score') + F('round4_score')).values(
        'podium_number').annotate(avg_score=Avg('round_total'))
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
                sorted_by_adv_pct[0]['podium']: 'green', sorted_by_adv_pct[1]['podium']: 'green',
                sorted_by_adv_pct[2]['podium']: 'red', sorted_by_adv_pct[3]['podium']: 'red',
            }
            for stat in advancement_stats: stat['advanced_pct_color'] = podium_color_map.get(stat['podium'], 'gray')

    # --- Fast Line & Leaderboards ---
    correct_counts = dict(
        Player.objects.filter(fast_line_correct_count__isnull=False).values_list('fast_line_correct_count').annotate(
            count=Count('id')))
    incorrect_counts = dict(Player.objects.filter(fast_line_incorrect_count__isnull=False).values_list(
        'fast_line_incorrect_count').annotate(count=Count('id')))
    chart_labels = list(range(13))
    correct_data = [correct_counts.get(i, 0) for i in range(13)]
    incorrect_data = [incorrect_counts.get(i, 0) for i in range(13)]
    avg_stats = Player.objects.aggregate(avg_correct=Avg('fast_line_correct_count'),
                                         avg_incorrect=Avg('fast_line_incorrect_count'))
    top_fast_line_players = Player.objects.select_related('game').filter(
        fast_line_correct_count__isnull=False).order_by('-fast_line_correct_count', 'fast_line_incorrect_count')[:5]
    top_fast_line_scores = Player.objects.annotate(
        round_total=Sum(F('round1_score') + F('round2_score') + F('round3_score') + F('round4_score'))).annotate(
        fast_line_total=F('round_total') + (F('fast_line_score') or 0)).filter(
        fast_line_score__isnull=False).select_related('game').order_by('-fast_line_total')[:20]
    leaderboard_data = Player.objects.annotate(
        round_total=Sum(F('round1_score') + F('round2_score') + F('round3_score') + F('round4_score'))).annotate(
        fast_line_total=F('round_total') + (F('fast_line_score') or 0)).select_related('game').order_by(
        '-total_winnings', '-fast_line_total')[:20]

    all_game_ids = list(Game.objects.values_list('id', flat=True).order_by('-air_date', '-episode_number'))
    leaderboard_players = list(top_fast_line_players) + list(top_fast_line_scores) + list(leaderboard_data) + [
        v['player'] for v in top_comebacks]
    game_ids_to_map = {p.game_id for p in leaderboard_players}
    game_page_map = {game_id: (all_game_ids.index(game_id) // 5) + 1 for game_id in game_ids_to_map if
                     game_id in all_game_ids}
    for p in leaderboard_players: p.page_number = game_page_map.get(p.game_id)

    # --- Final Round Performance ---
    final_round_counts = dict(Player.objects.filter(final_round_correct_count__isnull=False).values_list(
        'final_round_correct_count').annotate(count=Count('id')))
    total_final_round_players = sum(final_round_counts.values())
    final_round_stats = []
    for i in range(6):
        count = final_round_counts.get(i, 0)
        final_round_stats.append({'correct_count': i, 'count': count, 'pct': (
                    count / total_final_round_players * 100) if total_final_round_players > 0 else 0})
    color_code_dist(final_round_stats)

    # --- Top Podium Scores ---
    podium_leaderboards = []
    for i in range(1, 5):
        top_players = Player.objects.filter(podium_number=i).annotate(round_total=Sum(
            F('round1_score') + F('round2_score') + F('round3_score') + F('round4_score'))).select_related(
            'game').order_by('-round_total')[:10]
        for p in top_players: p.page_number = game_page_map.get(p.game_id)
        podium_leaderboards.append({'podium_number': i, 'players': top_players})

    # Serialize Player objects to IDs for JSON
    def serialize_player_list(players):
        return [{'id': p.id, 'name': p.name, 'podium_number': p.podium_number,
                 'game': {'id': p.game.id, 'air_date': p.game.air_date.isoformat()},
                 'fast_line_total': getattr(p, 'fast_line_total', None), 'total_winnings': p.total_winnings,
                 'final_round_correct_count': p.final_round_correct_count,
                 'fast_line_correct_count': p.fast_line_correct_count,
                 'fast_line_incorrect_count': p.fast_line_incorrect_count,
                 'round_total': getattr(p, 'round_total', None), 'page_number': p.page_number} for p in players]

    # --- Final Context ---
    context_data = {
        'latest_game_id': latest_game.id,
        'podium_stats': podium_stats,
        'advancement_stats': advancement_stats,
        'turn_performance': turn_performance,
        'preliminary_round_dist': preliminary_round_dist,
        'player_prelim_dist': player_prelim_dist,
        'player_advancement_dist': player_advancement_dist,
        'chart_labels': json.dumps(chart_labels),
        'correct_data': json.dumps(correct_data),
        'incorrect_data': json.dumps(incorrect_data),
        'avg_stats': avg_stats,
        'top_fast_line_players': serialize_player_list(top_fast_line_players),
        'final_round_stats': final_round_stats,
        'top_fast_line_scores': serialize_player_list(top_fast_line_scores),
        'leaderboard_data': serialize_player_list(leaderboard_data),
        'podium_leaderboards': [{'podium_number': pl['podium_number'], 'players': serialize_player_list(pl['players'])}
                                for pl in podium_leaderboards],
        'aggregate_stats': aggregate_stats,
        'come_from_behind_stats': come_from_behind_stats,
        'top_comebacks': [{'player': serialize_player_list([c['player']])[0], 'diff': c['diff']} for c in
                          top_comebacks],
    }

    StatisticsCache.objects.create(
        through_game=latest_game,
        data=context_data
    )


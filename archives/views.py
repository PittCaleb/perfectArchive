from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required, permission_required, user_passes_test
from .models import Game, Player, CustomUser, Syndication, StatisticsCache, PreliminaryLine, FastLine
import json
from django.core.paginator import Paginator
from django.db.models import Count, Avg, Q, Sum, F
from collections import defaultdict
from .stats_utils import update_statistics_cache
from .forms import PreliminaryLineForm, FastLineForm
from django.urls import reverse
from django.contrib import messages


def search_games_view(request):
    query = request.GET.get('q', '').strip()
    sort_col = request.GET.get('sort', 'total')
    sort_dir = request.GET.get('dir', 'desc')

    # Fetch all players to establish accurate populations and allow default display
    all_players = list(Player.objects.select_related('game').prefetch_related('game__players').all())

    prelim_correct_pop, prelim_score_pop = [], []
    fl_right_pop, fl_wrong_pop, fl_winnings_pop = [], [], []
    final_right_pop = []

    # We will only populate this with the winning score of each game
    total_winnings_pop = []
    winning_player_ids = set()
    processed_games_for_pop = set()

    # Build populations for math
    for p in all_players:
        # Determine the winner(s) of this game to build the winners-only population
        if p.game.id not in processed_games_for_pop:
            advancing_ids, winner_ids = _calculate_game_outcomes(p.game)
            for w_id in winner_ids:
                winning_player_ids.add(w_id)
                winner_obj = next((gp for gp in p.game.players.all() if gp.id == w_id), None)
                if winner_obj:
                    total_winnings_pop.append(winner_obj.total_winnings)
            processed_games_for_pop.add(p.game.id)

        rounds = [p.round1_correct, p.round2_correct, p.round3_correct, p.round4_correct]
        p_correct = sum(1 for r in rounds if r is True)
        prelim_correct_pop.append(p_correct)

        p_score = (p.round1_score or 0) + (p.round2_score or 0) + (p.round3_score or 0) + (p.round4_score or 0)
        prelim_score_pop.append(p_score)

        # FIX: Use fast_line_correct_count as the true flag for Fast Line participation
        if p.fast_line_correct_count is not None:
            fl_right_pop.append(p.fast_line_correct_count)

            if p.fast_line_incorrect_count is not None:
                fl_wrong_pop.append(p.fast_line_incorrect_count)

            # Append to Fast Line Winnings population ONLY if they played
            fl_score_val = p.fast_line_score if p.fast_line_score is not None else 0
            fl_winnings_pop.append(p_score + fl_score_val)

        if p.final_round_correct_count is not None:
            final_right_pop.append(p.final_round_correct_count)

    def get_stats(score, population, reverse=True):
        if score is None or not population:
            return None, None

        sorted_pop = sorted(population, reverse=reverse)
        # Rank: Ties get the best possible rank index (first occurrence)
        rank = sorted_pop.index(score) + 1
        total = len(population)

        # Percentile: Rank-based. Guarantees Rank 1 = 100%.
        # Represents the percentage of the population that ranked at or below this tier.
        percentile = round(((total - rank + 1) / total) * 100) if total > 0 else 0

        return rank, percentile

    results = []

    # Filter for the view based on search query
    view_players = [p for p in all_players if query.lower() in p.name.lower()] if query else all_players

    for mp in view_players:
        mp_rounds = [mp.round1_correct, mp.round2_correct, mp.round3_correct, mp.round4_correct]
        mp_prelim_correct = sum(1 for r in mp_rounds if r is True)
        mp_prelim_score = (mp.round1_score or 0) + (mp.round2_score or 0) + (mp.round3_score or 0) + (
                    mp.round4_score or 0)
        # Gatekeep the individual calculation so eliminated players get 'None'
        if mp.fast_line_correct_count is not None:
            fl_score_val = mp.fast_line_score if mp.fast_line_score is not None else 0
            mp_fl_winnings = mp_prelim_score + fl_score_val
        else:
            mp_fl_winnings = None
        c_rank, c_pct = get_stats(mp_prelim_correct, prelim_correct_pop)
        s_rank, s_pct = get_stats(mp_prelim_score, prelim_score_pop)
        fl_r_rank, fl_r_pct = get_stats(mp.fast_line_correct_count, fl_right_pop)
        fl_w_rank, fl_w_pct = get_stats(mp.fast_line_incorrect_count, fl_wrong_pop, reverse=False)
        fl_win_rank, fl_win_pct = get_stats(mp_fl_winnings, fl_winnings_pop)
        fin_r_rank, fin_r_pct = get_stats(mp.final_round_correct_count, final_right_pop)
        # Only rank the player against other winners if they actually won their game
        if mp.id in winning_player_ids:
            tot_rank, tot_pct = get_stats(mp.total_winnings, total_winnings_pop)
        else:
            tot_rank, tot_pct = None, None

        # Attach clean attributes for sorting
        mp.sort_show = mp.game.id
        mp.sort_date = mp.game.air_date
        mp.sort_name = mp.name.lower()
        mp.sort_podium = mp.podium_number
        mp.sort_prelim_correct = mp_prelim_correct
        mp.sort_prelim_score = mp_prelim_score
        mp.sort_fl_right = mp.fast_line_correct_count if mp.fast_line_correct_count is not None else -1
        mp.sort_fl_wrong = mp.fast_line_incorrect_count if mp.fast_line_incorrect_count is not None else 999
        mp.sort_fl_winnings = mp_fl_winnings if mp_fl_winnings is not None else -9999
        mp.sort_final_right = mp.final_round_correct_count if mp.final_round_correct_count is not None else -1
        mp.sort_total = mp.total_winnings

        mp.display_prelim_correct = {'raw': mp_prelim_correct, 'rank': c_rank, 'pct': c_pct}
        mp.display_prelim_score = {'raw': mp_prelim_score, 'rank': s_rank, 'pct': s_pct}

        if mp.fast_line_correct_count is not None:
            mp.display_fl_right = {'raw': mp.fast_line_correct_count, 'rank': fl_r_rank, 'pct': fl_r_pct}
            mp.display_fl_wrong = {'raw': mp.fast_line_incorrect_count, 'rank': fl_w_rank, 'pct': fl_w_pct}
            mp.display_fl_winnings = {'raw': mp_fl_winnings, 'rank': fl_win_rank, 'pct': fl_win_pct}
        else:
            mp.display_fl_right = mp.display_fl_wrong = mp.display_fl_winnings = None

        if mp.final_round_correct_count is not None:
            mp.display_final_right = {'raw': mp.final_round_correct_count, 'rank': fin_r_rank, 'pct': fin_r_pct}
        else:
            mp.display_final_right = None

        mp.display_total = {'raw': mp.total_winnings, 'rank': tot_rank, 'pct': tot_pct}

        results.append(mp)

    # Apply Sorting
    reverse_sort = (sort_dir == 'desc')
    sort_key_map = {
        'show': lambda x: x.sort_show, 'date': lambda x: x.sort_date, 'name': lambda x: x.sort_name,
        'podium': lambda x: x.sort_podium, 'prelim_correct': lambda x: x.sort_prelim_correct,
        'prelim_score': lambda x: x.sort_prelim_score, 'fl_right': lambda x: x.sort_fl_right,
        'fl_wrong': lambda x: x.sort_fl_wrong, 'fl_winnings': lambda x: x.sort_fl_winnings,
        'final_right': lambda x: x.sort_final_right, 'total': lambda x: x.sort_total,
    }

    if sort_col in sort_key_map:
        results.sort(key=sort_key_map[sort_col], reverse=reverse_sort)

    # Paginate (20 players per page)
    paginator = Paginator(results, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Process game outcomes ONLY for the players on the current page so the dropdown report works
    processed_games = set()
    for p in page_obj:
        game = p.game
        if game.id not in processed_games:
            advancing_ids, winner_ids = _calculate_game_outcomes(game)
            for gp in game.players.all():
                gp.is_advancing = gp.id in advancing_ids
                gp.is_winner = gp.id in winner_ids
                gp.round_total_score = gp.round1_score + gp.round2_score + gp.round3_score + gp.round4_score
                gp.fast_line_total_score = gp.round_total_score + (gp.fast_line_score or 0)
            processed_games.add(game.id)

    context = {
        'query': query,
        'page_obj': page_obj,
        'sort_col': sort_col,
        'sort_dir': sort_dir,
    }
    return render(request, 'archives/search_games.html', context)

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


# Admin Pages
@login_required
@permission_required('archives.add_game', raise_exception=True)
def game_admin_view(request):
    return render(request, 'archives/game_admin.html')


@login_required
@permission_required('archives.add_game', raise_exception=True)
def add_preliminary_line_view(request):
    if request.method == 'POST':
        form = PreliminaryLineForm(request.POST)
        if form.is_valid():
            instance = form.save()
            messages.success(request,
                             f"Successfully added line for Game {instance.game.id}, Round {instance.round_number}.")

            next_game_id = instance.game.id
            next_round_number = instance.round_number + 1
            if instance.round_number >= 4:
                next_game = Game.objects.filter(id__gt=instance.game.id).order_by('id').first()
                next_game_id = next_game.id if next_game else instance.game.id + 1
                next_round_number = 1

            return redirect(f"{reverse('add_line')}?game={next_game_id}&round_number={next_round_number}")
    else:
        initial_data = {
            'game': request.GET.get('game'),
            'round_number': request.GET.get('round_number')
        }
        if not initial_data['game']:
            last_line = PreliminaryLine.objects.order_by('-game__id', '-round_number').first()
            if last_line:
                next_game_id = last_line.game.id
                next_round_number = last_line.round_number + 1
                if next_round_number > 4:
                    next_round_number = 1
                    next_game_obj = Game.objects.filter(id__gt=last_line.game.id).order_by('id').first()
                    if next_game_obj:
                        next_game_id = next_game_obj.id
                    else:
                        next_game_id += 1
                initial_data['game'] = next_game_id
                initial_data['round_number'] = next_round_number
            else:
                first_game = Game.objects.order_by('id').first()
                if first_game:
                    initial_data['game'] = first_game.id
                    initial_data['round_number'] = 1

        form = PreliminaryLineForm(initial=initial_data)

    return render(request, 'archives/add_preliminary_line.html', {'form': form})


@login_required
@permission_required('archives.add_game', raise_exception=True)
def add_fast_line_view(request):
    if request.method == 'POST':
        form = FastLineForm(request.POST)
        if form.is_valid():
            instance = form.save()
            messages.success(request, f"Successfully added Fast Line for Game {instance.game.id}.")

            num_lines_for_game = FastLine.objects.filter(game=instance.game).count()
            if num_lines_for_game < 2:
                next_game_id = instance.game.id
            else:
                next_game = Game.objects.filter(id__gt=instance.game.id).order_by('id').first()
                next_game_id = next_game.id if next_game else instance.game.id + 1

            return redirect(f"{reverse('add_fast_line')}?game={next_game_id}")
    else:
        initial_data = {'game': request.GET.get('game')}
        if not initial_data['game']:
            last_fast_line = FastLine.objects.order_by('-game__id').first()
            if last_fast_line:
                num_lines_for_game = FastLine.objects.filter(game=last_fast_line.game).count()
                if num_lines_for_game < 2:
                    initial_data['game'] = last_fast_line.game.id
                else:
                    next_game = Game.objects.filter(id__gt=last_fast_line.game.id).order_by('id').first()
                    initial_data['game'] = next_game.id if next_game else last_fast_line.game.id + 1
            else:
                first_game = Game.objects.order_by('id').first()
                if first_game:
                    initial_data['game'] = first_game.id

        form = FastLineForm(initial=initial_data)

    return render(request, 'archives/add_fast_line.html', {'form': form})


@login_required
@permission_required('archives.add_game', raise_exception=True)
def add_final_line_view(request):
    return render(request, 'archives/add_final_line.html')


@login_required
@permission_required('archives.add_game', raise_exception=True)
def manage_leaderboards_view(request):
    return render(request, 'archives/manage_leaderboards.html')


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


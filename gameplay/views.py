from django.shortcuts import render
from django.contrib.auth.decorators import user_passes_test
from archives.models import CustomUser, PreliminaryLine, Game, Leaderboard
import json
import random
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from datetime import date, timedelta
from django.template.loader import render_to_string


def is_beta_tester_or_superuser(user):
    """
    Checks if a user is authenticated and has the BETA_TESTER role or is a superuser.
    """
    return user.is_authenticated and (user.role == CustomUser.Role.BETA_TESTER or user.is_superuser)


@user_passes_test(is_beta_tester_or_superuser)
def play_view(request):
    """
    The main landing page for the beta testing area.
    """
    return render(request, 'gameplay/play.html')


@user_passes_test(is_beta_tester_or_superuser)
def prelim_game_view(request):
    """
    Selects a random game and passes its preliminary line data and leaderboards to the template.
    """
    game_data = None
    all_game_ids = list(PreliminaryLine.objects.values_list('game_id', flat=True).distinct())

    if all_game_ids:
        random_game_id = random.choice(all_game_ids)
        lines = PreliminaryLine.objects.filter(game_id=random_game_id).order_by('round_number')

        rounds_data = {}
        for line in lines:
            rounds_data[line.round_number] = {
                'topic': line.topic,
                'orderDescription': line.order_description,
                'episodeCorrectCount': line.episode_correct_count,
                'items': [
                    {'name': line.seed_name, 'value': line.seed_value, 'order': line.seed_order, 'type': 'seed'},
                    {'name': line.item1_name, 'value': line.item1_value, 'order': line.item1_order, 'type': 'player'},
                    {'name': line.item2_name, 'value': line.item2_value, 'order': line.item2_order, 'type': 'player'},
                    {'name': line.item3_name, 'value': line.item3_value, 'order': line.item3_order, 'type': 'player'},
                    {'name': line.item4_name, 'value': line.item4_value, 'order': line.item4_order, 'type': 'player'},
                ]
            }

        game_data = {
            'gameId': random_game_id,
            'rounds': rounds_data
        }

    # Fetch Leaderboard Data for initial page load
    today = date.today()

    daily_scores = Leaderboard.objects.filter(
        game_type='prelim', play_type='solo', date__date=today
    ).select_related('game_played').order_by('-score')[:10]

    weekly_scores = Leaderboard.objects.filter(
        game_type='prelim', play_type='solo', date__date__gte=today - timedelta(days=7)
    ).select_related('game_played').order_by('-score')[:10]

    monthly_scores = Leaderboard.objects.filter(
        game_type='prelim', play_type='solo', date__date__gte=today - timedelta(days=30)
    ).select_related('game_played').order_by('-score')[:10]

    context = {
        'game_data_json': json.dumps(game_data),
        'daily_scores': daily_scores,
        'weekly_scores': weekly_scores,
        'monthly_scores': monthly_scores,
    }
    return render(request, 'gameplay/prelim_game.html', context)


@csrf_exempt
@user_passes_test(is_beta_tester_or_superuser)
def save_score_api(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            # Basic validation
            if not all([data.get('name'), data.get('score') is not None, data.get('game_type'), data.get('play_type'),
                        data.get('game_id')]):
                return JsonResponse({'message': 'Missing required data.'}, status=400)

            Leaderboard.objects.create(
                name=data.get('name'),
                score=data.get('score'),
                game_type=data.get('game_type'),
                play_type=data.get('play_type'),
                game_played_id=data.get('game_id')
            )
            return JsonResponse({'message': 'Score saved successfully!'}, status=201)
        except Exception as e:
            return JsonResponse({'message': f'An error occurred: {str(e)}'}, status=500)
    return JsonResponse({'message': 'Invalid request method'}, status=405)


@user_passes_test(is_beta_tester_or_superuser)
def get_leaderboard_api(request):
    """
    API endpoint to fetch and render leaderboard tables.
    """
    game_type = request.GET.get('game_type', 'prelim')
    play_type = request.GET.get('play_type', 'solo')
    today = date.today()

    daily_scores = Leaderboard.objects.filter(game_type=game_type, play_type=play_type,
                                              date__date=today).select_related('game_played').order_by('-score')[:10]
    weekly_scores = Leaderboard.objects.filter(game_type=game_type, play_type=play_type,
                                               date__date__gte=today - timedelta(days=7)).select_related(
        'game_played').order_by('-score')[:10]
    monthly_scores = Leaderboard.objects.filter(game_type=game_type, play_type=play_type,
                                                date__date__gte=today - timedelta(days=30)).select_related(
        'game_played').order_by('-score')[:10]

    daily_html = render_to_string('gameplay/leaderboard_table.html', {'scores': daily_scores, 'type': 'daily'})
    weekly_html = render_to_string('gameplay/leaderboard_table.html', {'scores': weekly_scores, 'type': 'weekly'})
    monthly_html = render_to_string('gameplay/leaderboard_table.html', {'scores': monthly_scores, 'type': 'monthly'})

    return JsonResponse({
        'daily_html': daily_html,
        'weekly_html': weekly_html,
        'monthly_html': monthly_html,
    })


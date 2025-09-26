from django.shortcuts import render
from django.contrib.auth.decorators import user_passes_test
from archives.models import CustomUser, PreliminaryLine
import json
import random


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
    Selects a random game and passes its preliminary line data to the template.
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

    context = {
        'game_data_json': json.dumps(game_data)
    }
    return render(request, 'gameplay/prelim_game.html', context)


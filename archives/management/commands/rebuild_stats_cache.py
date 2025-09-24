from django.core.management.base import BaseCommand
from archives.stats_utils import update_statistics_cache


class Command(BaseCommand):
    help = 'Recalculates all statistics and saves them to the StatisticsCache model.'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.NOTICE('Starting statistics cache rebuild...'))

        try:
            update_statistics_cache()
            self.stdout.write(self.style.SUCCESS('Successfully rebuilt and saved statistics cache!'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'An error occurred: {e}'))

# python manage.py rebuild_stats_cache
from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.conf import settings


class CustomUserManager(BaseUserManager):
    """Define a model manager for User model with no username field."""

    def _create_user(self, email, password=None, **extra_fields):
        """Create and save a User with the given email and password."""
        if not email:
            raise ValueError('The given email must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        """Create and save a SuperUser with the given email and password."""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', CustomUser.Role.ADMIN)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self._create_user(email, password, **extra_fields)


class CustomUser(AbstractUser):
    class Role(models.TextChoices):
        BASIC = 'BASIC', 'Basic'
        SECONDARY = 'SECONDARY', 'Secondary'
        SCOREKEEPER = 'SCOREKEEPER', 'Scorekeeper'
        BETA_TESTER = 'BETA_TESTER', 'Beta Tester'
        ADMIN = 'ADMIN', 'Admin'

    username = None
    email = models.EmailField('email address', unique=True)
    base_role = Role.BASIC
    role = models.CharField(max_length=50, choices=Role.choices, default=base_role)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    def save(self, *args, **kwargs):
        if not self.pk and not self.role:
            self.role = self.base_role
        return super().save(*args, **kwargs)


class Game(models.Model):
    air_date = models.DateField()
    episode_number = models.IntegerField(choices=[(1, '1'), (2, '2')])
    episode_title = models.CharField(max_length=255, blank=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='submitted_games'
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    fast_line_tiebreaker_winner_podium = models.IntegerField(null=True, blank=True)

    def __str__(self):
        return f"Ep {self.id}: {self.episode_title} ({self.air_date})"

    class Meta:
        ordering = ['-air_date', '-episode_number']
        unique_together = ('air_date', 'episode_number')


class Player(models.Model):
    game = models.ForeignKey(Game, related_name='players', on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    podium_number = models.IntegerField()
    round1_correct = models.BooleanField(null=True)
    round2_correct = models.BooleanField(null=True)
    round3_correct = models.BooleanField(null=True)
    round4_correct = models.BooleanField(null=True)
    round1_score = models.IntegerField(default=0)
    round2_score = models.IntegerField(default=0)
    round3_score = models.IntegerField(default=0)
    round4_score = models.IntegerField(default=0)
    won_tiebreaker = models.BooleanField(default=False)
    fast_line_correct_count = models.IntegerField(null=True, blank=True)
    fast_line_incorrect_count = models.IntegerField(null=True, blank=True)
    fast_line_score = models.IntegerField(null=True, default=None)
    final_round_correct_count = models.IntegerField(null=True, blank=True)
    total_winnings = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.name} in game on {self.game.air_date}"

    class Meta:
        ordering = ['game', 'podium_number']
        unique_together = ('game', 'podium_number')


class Syndication(models.Model):
    state = models.CharField(max_length=100)
    city = models.CharField(max_length=100)
    station = models.CharField(max_length=100)
    time = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.city}, {self.state} - {self.station}"

    class Meta:
        ordering = ['state', 'city']


class StatisticsCache(models.Model):
    updated_at = models.DateTimeField(auto_now_add=True)
    through_game = models.ForeignKey(Game, on_delete=models.CASCADE, null=True, blank=True)
    data = models.JSONField()

    def __str__(self):
        return f"Statistics Cache updated at {self.updated_at}"


class PreliminaryLine(models.Model):
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='preliminary_lines')
    round_number = models.IntegerField()
    topic = models.CharField(max_length=255)
    order_description = models.CharField(max_length=255, help_text="e.g., 'Lowest to Highest' or 'West to East'")

    seed_name = models.CharField(max_length=255)
    seed_value = models.CharField(max_length=100, blank=True, null=True)
    seed_order = models.IntegerField()

    item1_name = models.CharField(max_length=255)
    item1_value = models.CharField(max_length=100, blank=True, null=True)
    item1_order = models.IntegerField()

    item2_name = models.CharField(max_length=255)
    item2_value = models.CharField(max_length=100, blank=True, null=True)
    item2_order = models.IntegerField()

    item3_name = models.CharField(max_length=255)
    item3_value = models.CharField(max_length=100, blank=True, null=True)
    item3_order = models.IntegerField()

    item4_name = models.CharField(max_length=255)
    item4_value = models.CharField(max_length=100, blank=True, null=True)
    item4_order = models.IntegerField()

    episode_correct_count = models.IntegerField()

    def __str__(self):
        return f"Game {self.game.id}, Round {self.round_number}: {self.topic}"

    class Meta:
        ordering = ['game', 'round_number']
        unique_together = ('game', 'round_number')


class Leaderboard(models.Model):
    """
    Stores scores from the playable games.
    """
    GAME_TYPE_CHOICES = [('prelim', 'Preliminary'), ('fast', 'Fast Line'), ('final', 'Final Line')]
    PLAY_TYPE_CHOICES = [('solo', 'Solo'), ('ai', 'vs. AI'), ('multi', 'Multiplayer')]

    game_type = models.CharField(max_length=10, choices=GAME_TYPE_CHOICES)
    play_type = models.CharField(max_length=10, choices=PLAY_TYPE_CHOICES)
    name = models.CharField(max_length=100)
    score = models.IntegerField()
    game_played = models.ForeignKey(Game, on_delete=models.CASCADE)
    date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - ${self.score} ({self.get_game_type_display()} {self.get_play_type_display()})"

    class Meta:
        ordering = ['-score']


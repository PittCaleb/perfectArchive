from django.db import models
from django.contrib.auth.models import AbstractUser, Group, Permission, BaseUserManager
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
        ADMIN = 'ADMIN', 'Admin'

    # We don't need a username, email is our unique identifier
    username = None
    email = models.EmailField('email address', unique=True)
    base_role = Role.BASIC
    role = models.CharField(max_length=50, choices=Role.choices, default=base_role)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    def save(self, *args, **kwargs):
        if not self.pk:
            self.role = self.base_role
        return super().save(*args, **kwargs)


class Game(models.Model):
    """
    Represents a single game show episode.
    """
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

    def __str__(self):
        return f"{self.air_date} - {self.episode_title or f'Episode {self.episode_number}'}"

    class Meta:
        ordering = ['-air_date', '-episode_number']
        unique_together = ('air_date', 'episode_number')


class Player(models.Model):
    """
    Represents a single player's performance in one game.
    """
    game = models.ForeignKey(Game, related_name='players', on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    podium_number = models.IntegerField()

    # Round Results
    round1_correct = models.BooleanField(null=True)
    round2_correct = models.BooleanField(null=True)
    round3_correct = models.BooleanField(null=True)
    round4_correct = models.BooleanField(null=True)

    # Round Scores
    round1_score = models.IntegerField(null=False, blank=False, default=0)
    round2_score = models.IntegerField(null=False, blank=False, default=0)
    round3_score = models.IntegerField(null=False, blank=False, default=0)
    round4_score = models.IntegerField(null=False, blank=False, default=0)

    # Tiebreaker
    won_tiebreaker = models.BooleanField(default=False)

    # Fast Line
    fast_line_correct_count = models.IntegerField(null=True, blank=True)
    fast_line_incorrect_count = models.IntegerField(null=True, blank=True)
    fast_line_score = models.IntegerField(null=True, blank=False, default=None)

    # Final Round
    final_round_correct_count = models.IntegerField(null=True, blank=True)

    # Final Winnings
    total_winnings = models.IntegerField(null=False, blank=False, default=0)

    def __str__(self):
        return f"{self.name} in game on {self.game.air_date}"

    class Meta:
        ordering = ['game', 'podium_number']
        unique_together = ('game', 'podium_number')

class Syndication(models.Model):
    """
    Stores syndication information for the show.
    """
    state = models.CharField(max_length=100)
    city = models.CharField(max_length=100)
    station = models.CharField(max_length=100)
    time = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.city}, {self.state} - {self.station}"

    class Meta:
        ordering = ['state', 'city']

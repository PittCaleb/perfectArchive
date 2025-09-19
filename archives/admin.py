from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, Game, Player

class CustomUserAdmin(UserAdmin):
    """
    Configuration for the CustomUser model in the admin panel.
    """
    model = CustomUser
    # Use 'email' instead of 'username'
    list_display = ('email', 'role', 'is_staff', 'is_superuser')
    list_filter = ('role', 'is_staff', 'is_superuser')
    search_fields = ('email', 'role')
    # Use 'email' for ordering as 'username' does not exist
    ordering = ('email',)
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Permissions', {'fields': ('is_staff', 'is_active', 'role')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'role', 'password',),
        }),
    )

class PlayerInline(admin.TabularInline):
    """
    Allows editing Player objects directly within the Game admin page.
    """
    model = Player
    extra = 4 # Show 4 empty slots for players
    max_num = 4 # Do not allow more than 4 players
    can_delete = False
    readonly_fields = ('game',) # The game is set automatically

class GameAdmin(admin.ModelAdmin):
    """
    Configuration for the Game model in the admin panel.
    """
    # Use 'submitted_at' instead of 'created_at'
    list_display = ('air_date', 'episode_title', 'submitted_at', 'submitted_by')
    list_filter = ('air_date', 'submitted_by')
    search_fields = ('episode_title', 'air_date')
    ordering = ('-air_date',)
    inlines = [PlayerInline]

class PlayerAdmin(admin.ModelAdmin):
    """
    Configuration for the Player model in the admin panel.
    """
    # Use 'podium_number' and 'total_winnings'
    list_display = ('name', 'podium_number', 'game', 'total_winnings')
    list_filter = ('game__air_date',)
    search_fields = ('name', 'game__episode_title')
    ordering = ('-game__air_date', 'podium_number')

# Register your models here.
admin.site.register(CustomUser, CustomUserAdmin)
admin.site.register(Game, GameAdmin)
admin.site.register(Player, PlayerAdmin)

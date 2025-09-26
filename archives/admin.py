from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, Game, Player, Syndication, PreliminaryLine, StatisticsCache
from .forms import CustomUserCreationForm, CustomUserChangeForm


class CustomUserAdmin(UserAdmin):
    """
    Configuration for the CustomUser model in the admin panel.
    """
    # The forms to use for adding and changing user instances.
    form = CustomUserChangeForm
    add_form = CustomUserCreationForm

    model = CustomUser
    list_display = ('email', 'role', 'is_staff', 'is_active',)
    list_filter = ('role', 'is_staff', 'is_active',)

    # Fields to display on the "change" (edit) page
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'role')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )

    # Fields to display on the "add" page
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'role', 'password', 'password2'),
        }),
    )
    search_fields = ('email',)
    ordering = ('email',)


# Register your models here.
admin.site.register(CustomUser, CustomUserAdmin)
admin.site.register(Game)
admin.site.register(Player)
admin.site.register(Syndication)
admin.site.register(PreliminaryLine)
admin.site.register(StatisticsCache)


from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from .models import PreliminaryLine, Game, CustomUser

class CustomUserCreationForm(forms.ModelForm):
    """
    A form for creating new users. This custom form handles password
    creation and validation to work with an email-only user model.
    """
    password = forms.CharField(label='Password', widget=forms.PasswordInput)
    password2 = forms.CharField(label='Password confirmation', widget=forms.PasswordInput)

    class Meta:
        model = CustomUser
        fields = ('email', 'role')

    def clean_password2(self):
        # Check that the two password entries match
        password = self.cleaned_data.get("password")
        password2 = self.cleaned_data.get("password2")
        if password and password2 and password != password2:
            raise forms.ValidationError("Passwords don't match")
        return password2

    def save(self, commit=True):
        # Save the provided password in hashed format
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
        return user


class CustomUserChangeForm(UserChangeForm):
    """A form for updating users. Includes all the fields on
    the user, but replaces the password field with admin's
    password hash display field.
    """
    class Meta:
        model = CustomUser
        fields = ("email", "role", "is_active", "is_staff", "is_superuser")


class PreliminaryLineForm(forms.ModelForm):
    class Meta:
        model = PreliminaryLine
        fields = '__all__'
        widgets = {
            'order_description': forms.TextInput(attrs={'placeholder': 'e.g., Lowest to Highest'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['game'].queryset = Game.objects.order_by('-id')
        self.fields['game'].label_from_instance = lambda obj: f"Ep {obj.id}: {obj.episode_title}"


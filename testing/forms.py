from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.utils import timezone

from .models import (
    MOISTURE_MAX,
    MOISTURE_MIN,
    PH_MAX,
    PH_MIN,
    ContactMessage,
    FeedSample,
)

User = get_user_model()


class BootstrapFormMixin:
    """Apply Bootstrap 5 classes to widgets, including ``is-invalid`` on errors."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                css_class = 'form-check-input'
            elif isinstance(widget, forms.Select):
                css_class = 'form-select'
            else:
                css_class = 'form-control'
            self._add_class(widget, css_class)

    @staticmethod
    def _add_class(widget, css_class):
        existing = widget.attrs.get('class', '')
        if css_class not in existing.split():
            widget.attrs['class'] = f'{existing} {css_class}'.strip()

    def full_clean(self):
        super().full_clean()
        for name in self.errors:
            if name in self.fields:
                self._add_class(self.fields[name].widget, 'is-invalid')


class FeedSampleForm(BootstrapFormMixin, forms.ModelForm):
    """Collect a farmer's sample data and validate numeric/date values."""

    class Meta:
        model = FeedSample
        fields = (
            'sample_name',
            'feed_type',
            'collection_date',
            'ph_value',
            'moisture',
            'temperature',
            'smell',
            'mold_present',
            'observations',
        )
        labels = {
            'sample_name': 'Sample name or ID',
            'mold_present': 'Visible mold present',
        }
        help_texts = {
            'ph_value': 'Between 0 and 14.',
            'moisture': 'Percentage between 0 and 100.',
            'temperature': 'Enter degrees Celsius.',
            'observations': 'Optional notes about the sample.',
        }
        widgets = {
            # ``format`` lets the browser pre-fill the date when editing.
            'collection_date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'observations': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['ph_value'].widget.attrs.update(min=str(PH_MIN), max=str(PH_MAX))
        self.fields['moisture'].widget.attrs.update(min=str(MOISTURE_MIN), max=str(MOISTURE_MAX))
        self.fields['temperature'].widget.attrs.update(
            min=str(settings.SAMPLE_TEMPERATURE_MIN_C),
            max=str(settings.SAMPLE_TEMPERATURE_MAX_C),
            step='0.1',
        )
        self.fields['collection_date'].widget.attrs['max'] = timezone.localdate().isoformat()
        for name in ('ph_value', 'moisture', 'temperature', 'observations'):
            self.fields[name].widget.attrs['aria-describedby'] = f'id_{name}_helptext'

    def clean_collection_date(self):
        collection_date = self.cleaned_data['collection_date']
        if collection_date > timezone.localdate():
            raise forms.ValidationError('Collection date cannot be in the future.')
        return collection_date


class FarmerRegistrationForm(BootstrapFormMixin, UserCreationForm):
    """Create a Django user with a full name and email address."""

    full_name = forms.CharField(max_length=150, label='Full name')
    email = forms.EmailField(required=True)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email')

    field_order = ('full_name', 'username', 'email', 'password1', 'password2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        autocomplete = {
            'full_name': 'name',
            'username': 'username',
            'email': 'email',
            'password1': 'new-password',
            'password2': 'new-password',
        }
        for name, value in autocomplete.items():
            self.fields[name].widget.attrs['autocomplete'] = value
        self.fields['password1'].label = 'Password'
        self.fields['password2'].label = 'Confirm password'

    def clean_full_name(self):
        full_name = ' '.join(self.cleaned_data['full_name'].split())
        if not full_name:
            raise forms.ValidationError('Enter your full name.')
        return full_name

    def clean_email(self):
        email = self.cleaned_data['email'].strip()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('An account with this email address already exists.')
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        first_name, _, last_name = self.cleaned_data['full_name'].partition(' ')
        user.first_name = first_name
        user.last_name = last_name
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
        return user


class FarmerLoginForm(BootstrapFormMixin, AuthenticationForm):
    """Django's built-in username/password authentication form."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update(autocomplete='username', autofocus=True)
        self.fields['password'].widget.attrs['autocomplete'] = 'current-password'


class ContactForm(BootstrapFormMixin, forms.ModelForm):
    """Public contact form with a honeypot field to deter simple spam bots."""

    # Real visitors never see or fill this field (it is hidden with CSS).
    website = forms.CharField(
        required=False,
        label='Leave this field empty',
        widget=forms.TextInput(attrs={'tabindex': '-1', 'autocomplete': 'off'}),
    )

    class Meta:
        model = ContactMessage
        fields = ('name', 'email', 'message')
        widgets = {
            'name': forms.TextInput(attrs={'autocomplete': 'name'}),
            'email': forms.EmailInput(attrs={'autocomplete': 'email'}),
            'message': forms.Textarea(attrs={'rows': 4, 'maxlength': 2000}),
        }

    def clean_website(self):
        if self.cleaned_data.get('website'):
            raise forms.ValidationError('Spam detected.')
        return ''

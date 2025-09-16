from django import forms
from .models import AttendanceCheckpoint


class AttendanceCheckpointForm(forms.ModelForm):
    class Meta:
        model = AttendanceCheckpoint
        fields = ['checkpoint_type', 'name', 'description', 'required_time', 'grace_period_minutes', 'is_required', 'order']
        widgets = {
            'checkpoint_type': forms.Select(attrs={
                'class': 'form-control',
                'id': 'id_checkpoint_type'
            }),
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Entrance Check, 10 AM Check'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Optional description of this checkpoint',
                'rows': 3
            }),
            'required_time': forms.TimeInput(attrs={
                'class': 'form-control',
                'type': 'time'
            }),
            'grace_period_minutes': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'max': '60',
                'placeholder': '15'
            }),
            'is_required': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'order': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'placeholder': '1'
            }),
        }

    def __init__(self, *args, **kwargs):
        event = kwargs.pop('event', None)
        event_session = kwargs.pop('event_session', None)
        super().__init__(*args, **kwargs)
        
        # Set next order number
        if not self.instance.pk:  # New checkpoint
            if event:
                last_checkpoint = AttendanceCheckpoint.objects.filter(event=event).order_by('-order').first()
                self.fields['order'].initial = (last_checkpoint.order + 1) if last_checkpoint else 1
            elif event_session:
                last_checkpoint = AttendanceCheckpoint.objects.filter(event_session=event_session).order_by('-order').first()
                self.fields['order'].initial = (last_checkpoint.order + 1) if last_checkpoint else 1

    def clean(self):
        cleaned_data = super().clean()
        checkpoint_type = cleaned_data.get('checkpoint_type')
        name = cleaned_data.get('name')
        
        # Auto-generate name based on type if not provided
        if checkpoint_type and not name:
            type_names = {
                'entrance': 'Entrance Check',
                'hourly': 'Hourly Check',
                'break': 'Break Time',
                'lunch': 'Lunch Break',
                'activity': 'Activity Start',
                'exit': 'Exit Check',
                'custom': 'Custom Checkpoint'
            }
            cleaned_data['name'] = type_names.get(checkpoint_type, 'Custom Checkpoint')
        
        return cleaned_data


class QuickCheckpointForm(forms.Form):
    """Form for quickly setting up common checkpoint patterns"""
    PATTERN_CHOICES = [
        ('entrance_exit', 'Entrance + Exit Only'),
        ('hourly', 'Hourly Checks (Every Hour)'),
        ('entrance_lunch_exit', 'Entrance + Lunch + Exit'),
        ('entrance_breaks_exit', 'Entrance + Break Times + Exit'),
        ('custom', 'Custom Setup'),
    ]
    
    pattern = forms.ChoiceField(
        choices=PATTERN_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    # For hourly pattern
    start_time = forms.TimeField(
        required=False,
        widget=forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
        help_text="Start time for hourly checks"
    )
    end_time = forms.TimeField(
        required=False,
        widget=forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
        help_text="End time for hourly checks"
    )
    
    # For break pattern
    lunch_time = forms.TimeField(
        required=False,
        widget=forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
        initial='12:00'
    )
    morning_break = forms.TimeField(
        required=False,
        widget=forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
        initial='10:30'
    )
    afternoon_break = forms.TimeField(
        required=False,
        widget=forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
        initial='15:30'
    )
    
    grace_period = forms.IntegerField(
        initial=15,
        min_value=1,
        max_value=60,
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
        help_text="Grace period in minutes"
    )

    def clean(self):
        cleaned_data = super().clean()
        pattern = cleaned_data.get('pattern')
        
        if pattern == 'hourly':
            if not cleaned_data.get('start_time') or not cleaned_data.get('end_time'):
                raise forms.ValidationError("Start time and end time are required for hourly pattern.")
        
        return cleaned_data

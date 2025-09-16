from django import forms
from .models import Event, EventSession


class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = ['name', 'description', 'event_type', 'date', 'end_date', 'start_time', 'end_time', 'location']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter event name'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Enter event description',
                'rows': 4
            }),
            'event_type': forms.Select(attrs={
                'class': 'form-control',
                'id': 'id_event_type'
            }),
            'date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'end_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'start_time': forms.TimeInput(attrs={
                'class': 'form-control',
                'type': 'time'
            }),
            'end_time': forms.TimeInput(attrs={
                'class': 'form-control',
                'type': 'time'
            }),
            'location': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter event location'
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        event_type = cleaned_data.get('event_type')
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')
        date = cleaned_data.get('date')
        end_date = cleaned_data.get('end_date')

        if start_time and end_time and start_time >= end_time:
            raise forms.ValidationError("End time must be after start time.")

        if event_type in ['span', 'recurring']:
            if not end_date:
                raise forms.ValidationError("End date is required for multi-date events.")
            if date and end_date and end_date < date:
                raise forms.ValidationError("End date must be after start date.")

        return cleaned_data


class EventSessionForm(forms.ModelForm):
    class Meta:
        model = EventSession
        fields = ['session_date', 'start_time', 'end_time', 'location', 'notes']
        widgets = {
            'session_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'start_time': forms.TimeInput(attrs={
                'class': 'form-control',
                'type': 'time'
            }),
            'end_time': forms.TimeInput(attrs={
                'class': 'form-control',
                'type': 'time'
            }),
            'location': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter session location'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Session notes (optional)'
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')

        if start_time and end_time and start_time >= end_time:
            raise forms.ValidationError("End time must be after start time.")

        return cleaned_data

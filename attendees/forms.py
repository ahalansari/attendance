from django import forms
from .models import Attendee
import csv
import io


class AttendeeForm(forms.ModelForm):
    class Meta:
        model = Attendee
        fields = ['first_name', 'last_name', 'email', 'phone']
        widgets = {
            'first_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter first name'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter last name'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter email address'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter phone number'
            }),
        }


class BulkImportForm(forms.Form):
    csv_file = forms.FileField(
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.csv'
        }),
        help_text='Upload a CSV file with columns: first_name, last_name, email, phone'
    )

    def clean_csv_file(self):
        csv_file = self.cleaned_data['csv_file']
        if not csv_file.name.endswith('.csv'):
            raise forms.ValidationError('File must be a CSV file.')
        return csv_file

    def save(self, created_by):
        csv_file = self.cleaned_data['csv_file']
        decoded_file = csv_file.read().decode('utf-8')
        io_string = io.StringIO(decoded_file)
        reader = csv.DictReader(io_string)
        
        imported_count = 0
        for row in reader:
            attendee, created = Attendee.objects.get_or_create(
                email=row.get('email', ''),
                defaults={
                    'first_name': row.get('first_name', ''),
                    'last_name': row.get('last_name', ''),
                    'phone': row.get('phone', ''),
                    'created_by': created_by
                }
            )
            if created:
                imported_count += 1
        
        return imported_count

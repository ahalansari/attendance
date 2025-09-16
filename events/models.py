from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import uuid
import string
import random


class Event(models.Model):
    EVENT_TYPES = [
        ('single', 'Single Date Event'),
        ('recurring', 'Recurring Event'),
        ('span', 'Multi-Date Span Event'),
    ]
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES, default='single')
    date = models.DateField(help_text="Start date for single events, or first date for multi-date events")
    end_date = models.DateField(null=True, blank=True, help_text="End date for multi-date events")
    start_time = models.TimeField()
    end_time = models.TimeField()
    location = models.CharField(max_length=300)
    qr_code = models.CharField(max_length=50, unique=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)

    class Meta:
        ordering = ['-date', '-start_time']
        indexes = [
            models.Index(fields=['date', 'is_active']),
            models.Index(fields=['qr_code']),
        ]

    def __str__(self):
        return f"{self.name} - {self.date}"

    def save(self, *args, **kwargs):
        if not self.qr_code:
            self.qr_code = self.generate_unique_qr_code()
        super().save(*args, **kwargs)

    def generate_unique_qr_code(self):
        while True:
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))
            if not Event.objects.filter(qr_code=code).exists():
                return code

    @property
    def is_ongoing(self):
        now = timezone.now()
        event_datetime = timezone.datetime.combine(self.date, self.start_time)
        event_end_datetime = timezone.datetime.combine(self.date, self.end_time)
        event_datetime = timezone.make_aware(event_datetime)
        event_end_datetime = timezone.make_aware(event_end_datetime)
        return event_datetime <= now <= event_end_datetime

    @property
    def attendee_count(self):
        if self.event_type == 'single':
            return self.attendancerecord_set.count()
        else:
            # For multi-date events, count unique attendees across all sessions
            return self.attendancerecord_set.values('attendee').distinct().count()

    @property 
    def total_sessions(self):
        return self.eventsession_set.count()

    @property
    def duration_days(self):
        if self.end_date:
            return (self.end_date - self.date).days + 1
        return 1

    def generate_sessions(self):
        """Generate sessions for multi-date events"""
        if self.event_type in ['span', 'recurring'] and self.end_date:
            current_date = self.date
            while current_date <= self.end_date:
                EventSession.objects.get_or_create(
                    event=self,
                    session_date=current_date,
                    defaults={
                        'start_time': self.start_time,
                        'end_time': self.end_time,
                        'location': self.location,
                    }
                )
                current_date += timezone.timedelta(days=1)

    def get_current_day_checkpoints(self, target_date=None):
        """Get checkpoints for a specific date (or today if not specified)"""
        from attendance.models import AttendanceCheckpoint
        
        if target_date is None:
            target_date = timezone.now().date()
        
        if self.event_type == 'single':
            # For single events, return event-level checkpoints
            return AttendanceCheckpoint.objects.filter(
                event=self, is_active=True
            ).order_by('order')
        else:
            # For multi-day events, get checkpoints for specific date
            try:
                session = self.eventsession_set.get(session_date=target_date)
                # Return both event-level and session-specific checkpoints
                event_checkpoints = AttendanceCheckpoint.objects.filter(
                    event=self, event_session__isnull=True, is_active=True
                )
                session_checkpoints = AttendanceCheckpoint.objects.filter(
                    event_session=session, is_active=True
                )
                return (event_checkpoints | session_checkpoints).order_by('order')
            except:
                return AttendanceCheckpoint.objects.none()

    def get_available_dates(self):
        """Get all available dates for this event"""
        if self.event_type == 'single':
            return [self.date]
        elif self.end_date:
            dates = []
            current_date = self.date
            while current_date <= self.end_date:
                dates.append(current_date)
                current_date += timezone.timedelta(days=1)
            return dates
        return [self.date]


class EventSession(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    session_date = models.DateField()
    session_number = models.PositiveIntegerField(default=1)
    start_time = models.TimeField()
    end_time = models.TimeField()
    location = models.CharField(max_length=300)
    qr_code = models.CharField(max_length=50, unique=True, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['event', 'session_date']
        ordering = ['session_date', 'start_time']
        indexes = [
            models.Index(fields=['session_date', 'is_active']),
            models.Index(fields=['qr_code']),
        ]

    def __str__(self):
        return f"{self.event.name} - Session {self.session_number} ({self.session_date})"

    def save(self, *args, **kwargs):
        if not self.qr_code:
            self.qr_code = self.generate_unique_qr_code()
        
        # Auto-assign session number if not set
        if not self.session_number:
            last_session = EventSession.objects.filter(event=self.event).order_by('-session_number').first()
            self.session_number = (last_session.session_number if last_session else 0) + 1
            
        super().save(*args, **kwargs)

    def generate_unique_qr_code(self):
        while True:
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))
            if not EventSession.objects.filter(qr_code=code).exists():
                return code

    @property
    def is_ongoing(self):
        now = timezone.now()
        session_datetime = timezone.datetime.combine(self.session_date, self.start_time)
        session_end_datetime = timezone.datetime.combine(self.session_date, self.end_time)
        session_datetime = timezone.make_aware(session_datetime)
        session_end_datetime = timezone.make_aware(session_end_datetime)
        return session_datetime <= now <= session_end_datetime

    @property
    def attendee_count(self):
        return self.sessionattendance_set.count()
from django.db import models
from events.models import Event
from attendees.models import Attendee


class AttendanceRecord(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    attendee = models.ForeignKey(Attendee, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    device_fingerprint = models.TextField()
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField()
    
    # GPS Location fields
    latitude = models.DecimalField(max_digits=10, decimal_places=8, null=True, blank=True, help_text="GPS Latitude")
    longitude = models.DecimalField(max_digits=11, decimal_places=8, null=True, blank=True, help_text="GPS Longitude")
    location_accuracy = models.FloatField(null=True, blank=True, help_text="Location accuracy in meters")
    location_timestamp = models.DateTimeField(null=True, blank=True, help_text="When location was captured")

    class Meta:
        unique_together = ['event', 'attendee']
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['timestamp']),
            models.Index(fields=['event', 'attendee']),
            models.Index(fields=['latitude', 'longitude']),
        ]

    def __str__(self):
        return f"{self.attendee.attendee_id} - {self.event.name} - {self.timestamp}"


class SessionAttendance(models.Model):
    """Attendance for individual sessions of multi-date events"""
    event_session = models.ForeignKey('events.EventSession', on_delete=models.CASCADE)
    attendee = models.ForeignKey(Attendee, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    device_fingerprint = models.TextField()
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField()
    
    # GPS Location fields
    latitude = models.DecimalField(max_digits=10, decimal_places=8, null=True, blank=True, help_text="GPS Latitude")
    longitude = models.DecimalField(max_digits=11, decimal_places=8, null=True, blank=True, help_text="GPS Longitude")
    location_accuracy = models.FloatField(null=True, blank=True, help_text="Location accuracy in meters")
    location_timestamp = models.DateTimeField(null=True, blank=True, help_text="When location was captured")

    class Meta:
        unique_together = ['event_session', 'attendee']
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['timestamp']),
            models.Index(fields=['event_session', 'attendee']),
            models.Index(fields=['latitude', 'longitude']),
        ]

    def __str__(self):
        return f"{self.attendee.attendee_id} - {self.event_session} - {self.timestamp}"


class AttendanceCheckpoint(models.Model):
    """Defines required attendance checkpoints for events/sessions"""
    CHECKPOINT_TYPES = [
        ('entrance', 'Entrance'),
        ('hourly', 'Hourly Check'),
        ('break', 'Break Time'),
        ('lunch', 'Lunch Break'),
        ('activity', 'Activity Start'),
        ('exit', 'Exit'),
        ('custom', 'Custom'),
    ]
    
    APPLIES_TO_CHOICES = [
        ('all_days', 'All Days'),
        ('specific_day', 'Specific Day Only'),
        ('weekdays', 'Weekdays Only'),
        ('weekends', 'Weekends Only'),
    ]
    
    event = models.ForeignKey('events.Event', on_delete=models.CASCADE, null=True, blank=True)
    event_session = models.ForeignKey('events.EventSession', on_delete=models.CASCADE, null=True, blank=True)
    
    # New fields for multi-day event handling
    applies_to = models.CharField(max_length=20, choices=APPLIES_TO_CHOICES, default='all_days')
    specific_date = models.DateField(null=True, blank=True, help_text="For specific_day checkpoints only")
    
    checkpoint_type = models.CharField(max_length=20, choices=CHECKPOINT_TYPES, default='custom')
    name = models.CharField(max_length=100, help_text="e.g., 'Entrance', '10 AM Check', 'Lunch Break'")
    description = models.TextField(blank=True)
    
    # Timing configuration
    required_time = models.TimeField(help_text="Required time for this checkpoint")
    grace_period_minutes = models.PositiveIntegerField(default=15, help_text="Minutes before/after required time")
    
    # Checkpoint settings
    is_required = models.BooleanField(default=True, help_text="Must attendees complete this checkpoint?")
    order = models.PositiveIntegerField(default=1, help_text="Order of checkpoint (1, 2, 3...)")
    is_active = models.BooleanField(default=True)
    checkpoint_code = models.CharField(max_length=50, unique=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey('auth.User', on_delete=models.CASCADE)

    class Meta:
        ordering = ['order', 'required_time']
        unique_together = [
            ['event', 'order'],
            ['event_session', 'order'],
        ]
        indexes = [
            models.Index(fields=['required_time', 'is_active']),
            models.Index(fields=['event', 'order']),
            models.Index(fields=['event_session', 'order']),
            models.Index(fields=['checkpoint_code']),
        ]

    def __str__(self):
        event_name = self.event.name if self.event else self.event_session.event.name
        return f"{event_name} - {self.name} ({self.required_time})"

    def save(self, *args, **kwargs):
        if not self.checkpoint_code:
            self.checkpoint_code = self.generate_unique_checkpoint_code()
        super().save(*args, **kwargs)

    def generate_unique_checkpoint_code(self):
        import random
        import string
        while True:
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))
            if not AttendanceCheckpoint.objects.filter(checkpoint_code=code).exists():
                return code

    @property
    def window_start(self):
        """Calculate the start time of the attendance window"""
        from datetime import datetime, timedelta
        dt = datetime.combine(datetime.today(), self.required_time)
        window_start = dt - timedelta(minutes=self.grace_period_minutes)
        return window_start.time()

    @property
    def window_end(self):
        """Calculate the end time of the attendance window"""
        from datetime import datetime, timedelta
        dt = datetime.combine(datetime.today(), self.required_time)
        window_end = dt + timedelta(minutes=self.grace_period_minutes)
        return window_end.time()

    def is_within_window(self, current_time):
        """Check if current time is within the checkpoint window"""
        return self.window_start <= current_time <= self.window_end

    def applies_to_date(self, target_date):
        """Check if this checkpoint applies to the given date"""
        if self.applies_to == 'all_days':
            return True
        elif self.applies_to == 'specific_day':
            return self.specific_date == target_date
        elif self.applies_to == 'weekdays':
            return target_date.weekday() < 5  # Monday=0, Sunday=6
        elif self.applies_to == 'weekends':
            return target_date.weekday() >= 5
        return True


class CheckpointAttendance(models.Model):
    """Records attendance for specific checkpoints"""
    checkpoint = models.ForeignKey(AttendanceCheckpoint, on_delete=models.CASCADE)
    attendee = models.ForeignKey('attendees.Attendee', on_delete=models.CASCADE)
    
    # Regular event or session reference
    event = models.ForeignKey('events.Event', on_delete=models.CASCADE, null=True, blank=True)
    event_session = models.ForeignKey('events.EventSession', on_delete=models.CASCADE, null=True, blank=True)
    
    timestamp = models.DateTimeField(auto_now_add=True)
    device_fingerprint = models.TextField()
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField()
    
    # GPS Location fields
    latitude = models.DecimalField(max_digits=10, decimal_places=8, null=True, blank=True, help_text="GPS Latitude")
    longitude = models.DecimalField(max_digits=11, decimal_places=8, null=True, blank=True, help_text="GPS Longitude")
    location_accuracy = models.FloatField(null=True, blank=True, help_text="Location accuracy in meters")
    location_timestamp = models.DateTimeField(null=True, blank=True, help_text="When location was captured")
    
    # Status tracking
    is_on_time = models.BooleanField(default=True, help_text="Was attendance recorded within the time window?")
    is_late = models.BooleanField(default=False, help_text="Was attendance recorded after the grace period?")
    
    class Meta:
        unique_together = [
            ['checkpoint', 'attendee', 'event'],
            ['checkpoint', 'attendee', 'event_session'],
        ]
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['timestamp']),
            models.Index(fields=['checkpoint', 'attendee']),
            models.Index(fields=['is_on_time', 'is_late']),
            models.Index(fields=['latitude', 'longitude']),
        ]

    def __str__(self):
        return f"{self.attendee.attendee_id} - {self.checkpoint.name} - {self.timestamp}"

    def save(self, *args, **kwargs):
        # Calculate if attendance is on time or late
        current_time = self.timestamp.time()
        
        if self.checkpoint.is_within_window(current_time):
            self.is_on_time = True
            self.is_late = False
        elif current_time > self.checkpoint.window_end:
            self.is_on_time = False
            self.is_late = True
        else:
            # Too early
            self.is_on_time = False
            self.is_late = False
            
        super().save(*args, **kwargs)


class DeviceFootprint(models.Model):
    attendance_record = models.OneToOneField(AttendanceRecord, on_delete=models.CASCADE, null=True, blank=True)
    session_attendance = models.OneToOneField(SessionAttendance, on_delete=models.CASCADE, null=True, blank=True)
    checkpoint_attendance = models.OneToOneField(CheckpointAttendance, on_delete=models.CASCADE, null=True, blank=True)
    screen_resolution = models.CharField(max_length=20, blank=True)
    timezone = models.CharField(max_length=50, blank=True)
    language = models.CharField(max_length=10, blank=True)
    platform = models.CharField(max_length=50, blank=True)
    browser_fingerprint = models.TextField(blank=True)

    def __str__(self):
        if self.attendance_record:
            return f"Device info for {self.attendance_record}"
        elif self.session_attendance:
            return f"Device info for {self.session_attendance}"
        elif self.checkpoint_attendance:
            return f"Device info for {self.checkpoint_attendance}"
        return "Device info"
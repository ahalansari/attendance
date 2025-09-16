from django.db import models
from django.contrib.auth.models import User
import random
import string


class Attendee(models.Model):
    attendee_id = models.CharField(max_length=5, unique=True, blank=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)

    class Meta:
        ordering = ['attendee_id']
        indexes = [
            models.Index(fields=['attendee_id']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"{self.attendee_id} - {self.first_name} {self.last_name}"

    def save(self, *args, **kwargs):
        if not self.attendee_id:
            self.attendee_id = self.generate_unique_attendee_id()
        super().save(*args, **kwargs)

    def generate_unique_attendee_id(self):
        while True:
            attendee_id = ''.join(random.choices(string.digits, k=5))
            if not Attendee.objects.filter(attendee_id=attendee_id).exists():
                return attendee_id

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def total_events_attended(self):
        return self.attendancerecord_set.count()
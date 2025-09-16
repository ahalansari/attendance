from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.db.models import Count
from django.utils import timezone
from datetime import datetime, timedelta
from events.models import Event
from attendees.models import Attendee
from attendance.models import AttendanceRecord


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'accounts/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get basic stats
        context['total_events'] = Event.objects.filter(is_active=True).count()
        context['total_attendees'] = Attendee.objects.filter(is_active=True).count()
        
        # Today's attendance
        today = timezone.now().date()
        context['today_attendance'] = AttendanceRecord.objects.filter(
            timestamp__date=today
        ).count()
        
        # Recent events
        context['recent_events'] = Event.objects.filter(
            is_active=True
        ).order_by('-created_at')[:5]
        
        # Recent attendance records
        context['recent_attendance'] = AttendanceRecord.objects.select_related(
            'event', 'attendee'
        ).order_by('-timestamp')[:10]
        
        # This week's stats
        week_ago = today - timedelta(days=7)
        context['week_attendance'] = AttendanceRecord.objects.filter(
            timestamp__date__gte=week_ago
        ).count()
        
        # Active events today
        context['active_events_today'] = Event.objects.filter(
            date=today,
            is_active=True
        )
        
        return context
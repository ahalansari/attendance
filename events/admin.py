from django.contrib import admin
from .models import Event, EventSession


class EventSessionInline(admin.TabularInline):
    model = EventSession
    extra = 0
    readonly_fields = ['qr_code', 'session_number', 'created_at']


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ['name', 'event_type', 'date', 'end_date', 'start_time', 'end_time', 'location', 'is_active']
    list_filter = ['event_type', 'date', 'is_active', 'created_at']
    search_fields = ['name', 'location', 'qr_code']
    readonly_fields = ['qr_code', 'created_at', 'created_by']
    inlines = [EventSessionInline]
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
        
        # Generate sessions for multi-date events if this is a new event
        if not change and obj.event_type in ['span', 'recurring']:
            obj.generate_sessions()


@admin.register(EventSession)
class EventSessionAdmin(admin.ModelAdmin):
    list_display = ['event', 'session_number', 'session_date', 'start_time', 'end_time', 'location', 'is_active']
    list_filter = ['session_date', 'is_active', 'event__name']
    search_fields = ['event__name', 'qr_code', 'location']
    readonly_fields = ['qr_code', 'session_number', 'created_at']
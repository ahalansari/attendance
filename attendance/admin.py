from django.contrib import admin
from .models import AttendanceRecord, DeviceFootprint, SessionAttendance, AttendanceCheckpoint, CheckpointAttendance


class DeviceFootprintInline(admin.StackedInline):
    model = DeviceFootprint
    extra = 0
    readonly_fields = ['screen_resolution', 'timezone', 'language', 'platform', 'browser_fingerprint']


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ['attendee', 'event', 'timestamp', 'ip_address', 'has_location']
    list_filter = ['timestamp', 'event']
    search_fields = ['attendee__attendee_id', 'attendee__first_name', 'attendee__last_name', 'event__name']
    readonly_fields = ['timestamp', 'device_fingerprint', 'ip_address', 'user_agent', 'latitude', 'longitude', 'location_accuracy', 'location_timestamp']
    inlines = [DeviceFootprintInline]
    
    def has_location(self, obj):
        return obj.latitude is not None and obj.longitude is not None
    has_location.boolean = True
    has_location.short_description = 'GPS Location'


@admin.register(SessionAttendance)
class SessionAttendanceAdmin(admin.ModelAdmin):
    list_display = ['attendee', 'event_session', 'timestamp', 'ip_address', 'has_location']
    list_filter = ['timestamp', 'event_session__event', 'event_session__session_date']
    search_fields = ['attendee__attendee_id', 'attendee__first_name', 'attendee__last_name', 'event_session__event__name']
    readonly_fields = ['timestamp', 'device_fingerprint', 'ip_address', 'user_agent', 'latitude', 'longitude', 'location_accuracy', 'location_timestamp']
    inlines = [DeviceFootprintInline]
    
    def has_location(self, obj):
        return obj.latitude is not None and obj.longitude is not None
    has_location.boolean = True
    has_location.short_description = 'GPS Location'


@admin.register(AttendanceCheckpoint)
class AttendanceCheckpointAdmin(admin.ModelAdmin):
    list_display = ['name', 'checkpoint_type', 'get_event_name', 'required_time', 'order', 'is_required', 'is_active']
    list_filter = ['checkpoint_type', 'is_required', 'is_active', 'event__name']
    search_fields = ['name', 'event__name', 'event_session__event__name']
    readonly_fields = ['checkpoint_code', 'created_at']
    ordering = ['event', 'event_session', 'order']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'checkpoint_type', 'description', 'checkpoint_code')
        }),
        ('Event Association', {
            'fields': ('event', 'event_session')
        }),
        ('Timing', {
            'fields': ('required_time', 'grace_period_minutes')
        }),
        ('Settings', {
            'fields': ('order', 'is_required', 'is_active')
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_event_name(self, obj):
        if obj.event:
            return obj.event.name
        elif obj.event_session:
            return f"{obj.event_session.event.name} (Session {obj.event_session.session_number})"
        return "-"
    get_event_name.short_description = 'Event'
    
    def save_model(self, request, obj, form, change):
        if not change:  # Only set created_by for new objects
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(CheckpointAttendance)
class CheckpointAttendanceAdmin(admin.ModelAdmin):
    list_display = ['attendee', 'checkpoint', 'get_event_name', 'timestamp', 'is_on_time', 'is_late', 'ip_address', 'has_location']
    list_filter = ['timestamp', 'is_on_time', 'is_late', 'checkpoint__checkpoint_type']
    search_fields = ['attendee__attendee_id', 'attendee__first_name', 'attendee__last_name', 'checkpoint__name']
    readonly_fields = ['timestamp', 'is_on_time', 'is_late', 'latitude', 'longitude', 'location_accuracy', 'location_timestamp']
    inlines = [DeviceFootprintInline]
    
    def get_event_name(self, obj):
        if obj.event:
            return obj.event.name
        elif obj.event_session:
            return f"{obj.event_session.event.name} (Session {obj.event_session.session_number})"
        return "-"
    get_event_name.short_description = 'Event'
    
    def has_location(self, obj):
        return obj.latitude is not None and obj.longitude is not None
    has_location.boolean = True
    has_location.short_description = 'GPS Location'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'attendee', 'checkpoint', 'event', 'event_session__event'
        )
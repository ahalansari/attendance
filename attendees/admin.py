from django.contrib import admin
from .models import Attendee


@admin.register(Attendee)
class AttendeeAdmin(admin.ModelAdmin):
    list_display = ['attendee_id', 'first_name', 'last_name', 'email', 'phone', 'is_active']
    list_filter = ['is_active', 'created_at']
    search_fields = ['attendee_id', 'first_name', 'last_name', 'email']
    readonly_fields = ['attendee_id', 'created_at', 'created_by']
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
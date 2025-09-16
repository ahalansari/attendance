from django.shortcuts import render, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, TemplateView, View
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.utils import timezone
from decimal import Decimal
import json
from .models import AttendanceRecord, DeviceFootprint, SessionAttendance, AttendanceCheckpoint, CheckpointAttendance
from events.models import Event, EventSession
from attendees.models import Attendee


class AttendanceRecordListView(LoginRequiredMixin, ListView):
    model = AttendanceRecord
    template_name = 'attendance/records.html'
    context_object_name = 'records'
    paginate_by = 50

    def get_queryset(self):
        return AttendanceRecord.objects.select_related(
            'event', 'attendee'
        ).order_by('-timestamp')


class ScanView(TemplateView):
    template_name = 'attendance/unified_scan.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qr_code = kwargs.get('qr_code')
        
        try:
            event = Event.objects.get(qr_code=qr_code, is_active=True)
            context['event'] = event
            context['valid_qr'] = True
            
            # Get current date
            from django.utils import timezone
            current_date = timezone.now().date()
            
            # Get available dates for this event
            context['available_dates'] = event.get_available_dates()
            
            # Get current day's checkpoints
            current_checkpoints = event.get_current_day_checkpoints(current_date)
            context['current_checkpoints'] = current_checkpoints
            context['current_date'] = current_date
            
            # Check if current date is within event range
            context['is_valid_date'] = current_date in event.get_available_dates()
            
        except Event.DoesNotExist:
            context['valid_qr'] = False
            context['error'] = 'Invalid QR code or event not found.'
        
        return context


@method_decorator(csrf_exempt, name='dispatch')
class RecordUnifiedAttendanceView(View):
    """Record attendance for events with dynamic checkpoint selection and GPS location"""
    def post(self, request):
        try:
            data = json.loads(request.body)
            qr_code = data.get('qr_code')
            attendee_id = data.get('attendee_id')
            checkpoint_id = data.get('checkpoint_id')  # Can be None for simple attendance
            target_date = data.get('target_date')  # Optional, defaults to today
            device_info = data.get('device_info', {})
            location_data = data.get('location')  # GPS location data
            location_error = data.get('location_error')  # Location error if any
            
            # Validate event
            try:
                event = Event.objects.get(qr_code=qr_code, is_active=True)
            except Event.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid QR code or event not found.'
                })
            
            # Parse target date
            from django.utils import timezone
            if target_date:
                from datetime import datetime
                target_date = datetime.strptime(target_date, '%Y-%m-%d').date()
            else:
                target_date = timezone.now().date()
            
            # Validate date is within event range
            if target_date not in event.get_available_dates():
                return JsonResponse({
                    'success': False,
                    'error': f'Date {target_date} is not valid for this event.'
                })
            
            # Validate attendee
            try:
                attendee = Attendee.objects.get(attendee_id=attendee_id, is_active=True)
            except Attendee.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid attendee ID.'
                })
            
            # Get client IP
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip = x_forwarded_for.split(',')[0]
            else:
                ip = request.META.get('REMOTE_ADDR')
            
            # Prepare location fields
            latitude = None
            longitude = None
            location_accuracy = None
            location_timestamp = None
            
            if location_data:
                try:
                    latitude = Decimal(str(location_data.get('latitude')))
                    longitude = Decimal(str(location_data.get('longitude')))
                    location_accuracy = float(location_data.get('accuracy', 0))
                    if location_data.get('timestamp'):
                        from datetime import datetime
                        location_timestamp = datetime.fromisoformat(location_data['timestamp'].replace('Z', '+00:00'))
                except (ValueError, TypeError) as e:
                    # If location data is invalid, log it but continue
                    location_error = f"Invalid location data: {str(e)}"
            
            # Handle checkpoint attendance
            if checkpoint_id:
                try:
                    checkpoint = AttendanceCheckpoint.objects.get(id=checkpoint_id, is_active=True)
                    
                    # Validate checkpoint applies to target date
                    if not checkpoint.applies_to_date(target_date):
                        return JsonResponse({
                            'success': False,
                            'error': f'Checkpoint "{checkpoint.name}" is not available for {target_date}.'
                        })
                    
                    # Find the correct event session for multi-day events
                    event_session = None
                    if event.event_type != 'single':
                        try:
                            event_session = EventSession.objects.get(
                                event=event,
                                date=target_date
                            )
                        except EventSession.DoesNotExist:
                            return JsonResponse({
                                'success': False,
                                'error': f'No session found for {target_date}.'
                            })
                    
                    # Check if already attended this checkpoint
                    existing_checkpoint_attendance = CheckpointAttendance.objects.filter(
                        checkpoint=checkpoint,
                        attendee=attendee,
                        event=event if event.event_type == 'single' else None,
                        event_session=event_session
                    ).first()
                    
                    if existing_checkpoint_attendance:
                        return JsonResponse({
                            'success': False,
                            'error': f'Attendance already recorded for checkpoint "{checkpoint.name}".'
                        })
                    
                    # Create checkpoint attendance record
                    checkpoint_attendance = CheckpointAttendance.objects.create(
                        checkpoint=checkpoint,
                        attendee=attendee,
                        event=event if event.event_type == 'single' else None,
                        event_session=event_session,
                        device_fingerprint=str(device_info),
                        ip_address=ip,
                        user_agent=request.META.get('HTTP_USER_AGENT', ''),
                        latitude=latitude,
                        longitude=longitude,
                        location_accuracy=location_accuracy,
                        location_timestamp=location_timestamp
                    )
                    
                    # Create device footprint
                    DeviceFootprint.objects.create(
                        checkpoint_attendance=checkpoint_attendance,
                        screen_resolution=device_info.get('screen', ''),
                        timezone=device_info.get('timezone', ''),
                        language=device_info.get('language', ''),
                        platform=device_info.get('platform', ''),
                        browser_fingerprint=str(device_info)
                    )
                    
                    # Determine status
                    status = 'on_time'
                    if checkpoint_attendance.is_late:
                        status = 'late'
                    elif not checkpoint_attendance.is_on_time and not checkpoint_attendance.is_late:
                        status = 'early'
                    
                    return JsonResponse({
                        'success': True,
                        'message': f'Checkpoint attendance recorded successfully!',
                        'attendee_name': attendee.name,
                        'event_name': event.name,
                        'checkpoint_name': checkpoint.name,
                        'status': status,
                        'timestamp': checkpoint_attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                        'location_captured': latitude is not None and longitude is not None,
                        'location_error': location_error
                    })
                    
                except AttendanceCheckpoint.DoesNotExist:
                    return JsonResponse({
                        'success': False,
                        'error': 'Invalid checkpoint ID.'
                    })
            
            # Handle regular attendance (no checkpoint)
            else:
                if event.event_type == 'single':
                    # Single event - use AttendanceRecord
                    existing_attendance = AttendanceRecord.objects.filter(
                        event=event,
                        attendee=attendee
                    ).first()
                    
                    if existing_attendance:
                        return JsonResponse({
                            'success': False,
                            'error': 'Attendance already recorded for this event.'
                        })
                    
                    attendance_record = AttendanceRecord.objects.create(
                        event=event,
                        attendee=attendee,
                        device_fingerprint=str(device_info),
                        ip_address=ip,
                        user_agent=request.META.get('HTTP_USER_AGENT', ''),
                        latitude=latitude,
                        longitude=longitude,
                        location_accuracy=location_accuracy,
                        location_timestamp=location_timestamp
                    )
                    
                    # Create device footprint
                    DeviceFootprint.objects.create(
                        attendance_record=attendance_record,
                        screen_resolution=device_info.get('screen', ''),
                        timezone=device_info.get('timezone', ''),
                        language=device_info.get('language', ''),
                        platform=device_info.get('platform', ''),
                        browser_fingerprint=str(device_info)
                    )
                    
                    return JsonResponse({
                        'success': True,
                        'message': 'Attendance recorded successfully!',
                        'attendee_name': attendee.name,
                        'event_name': event.name,
                        'timestamp': attendance_record.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                        'location_captured': latitude is not None and longitude is not None,
                        'location_error': location_error
                    })
                    
                else:
                    # Multi-day event - use SessionAttendance
                    try:
                        event_session = EventSession.objects.get(
                            event=event,
                            date=target_date
                        )
                    except EventSession.DoesNotExist:
                        return JsonResponse({
                            'success': False,
                            'error': f'No session found for {target_date}.'
                        })
                    
                    existing_session_attendance = SessionAttendance.objects.filter(
                        event_session=event_session,
                        attendee=attendee
                    ).first()
                    
                    if existing_session_attendance:
                        return JsonResponse({
                            'success': False,
                            'error': f'Attendance already recorded for {target_date}.'
                        })
                    
                    session_attendance = SessionAttendance.objects.create(
                        event_session=event_session,
                        attendee=attendee,
                        device_fingerprint=str(device_info),
                        ip_address=ip,
                        user_agent=request.META.get('HTTP_USER_AGENT', ''),
                        latitude=latitude,
                        longitude=longitude,
                        location_accuracy=location_accuracy,
                        location_timestamp=location_timestamp
                    )
                    
                    # Create device footprint
                    DeviceFootprint.objects.create(
                        session_attendance=session_attendance,
                        screen_resolution=device_info.get('screen', ''),
                        timezone=device_info.get('timezone', ''),
                        language=device_info.get('language', ''),
                        platform=device_info.get('platform', ''),
                        browser_fingerprint=str(device_info)
                    )
                    
                    return JsonResponse({
                        'success': True,
                        'message': f'Session attendance recorded successfully!',
                        'attendee_name': attendee.name,
                        'event_name': f"{event.name} - {target_date}",
                        'timestamp': session_attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                        'location_captured': latitude is not None and longitude is not None,
                        'location_error': location_error
                    })
            
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON data.'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'Server error: {str(e)}'
            })


class GetEventCheckpointsView(View):
    """Get checkpoints for an event on a specific date"""
    def get(self, request, event_id):
        try:
            event = Event.objects.get(id=event_id, is_active=True)
            target_date = request.GET.get('date', timezone.now().date())
            
            if isinstance(target_date, str):
                from datetime import datetime
                target_date = datetime.strptime(target_date, '%Y-%m-%d').date()
            
            checkpoints = event.get_current_day_checkpoints(target_date)
            
            checkpoints_data = []
            for checkpoint in checkpoints:
                checkpoints_data.append({
                    'id': checkpoint.id,
                    'name': checkpoint.name,
                    'description': checkpoint.description,
                    'checkpoint_type': checkpoint.checkpoint_type,
                    'required_time': checkpoint.required_time.strftime('%H:%M'),
                    'window_start': checkpoint.window_start.strftime('%H:%M'),
                    'window_end': checkpoint.window_end.strftime('%H:%M'),
                    'is_required': checkpoint.is_required,
                    'order': checkpoint.order
                })
            
            return JsonResponse({
                'success': True,
                'checkpoints': checkpoints_data
            })
            
        except Event.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Event not found.'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'Error: {str(e)}'
            })


class GetSessionCheckpointsView(View):
    """Get checkpoints for a specific session"""
    def get(self, request, session_id):
        try:
            session = EventSession.objects.get(id=session_id)
            
            # Get session-specific checkpoints
            checkpoints = AttendanceCheckpoint.objects.filter(
                event_session=session,
                is_active=True
            ).order_by('order', 'required_time')
            
            checkpoints_data = []
            for checkpoint in checkpoints:
                checkpoints_data.append({
                    'id': checkpoint.id,
                    'name': checkpoint.name,
                    'description': checkpoint.description,
                    'checkpoint_type': checkpoint.checkpoint_type,
                    'required_time': checkpoint.required_time.strftime('%H:%M'),
                    'window_start': checkpoint.window_start.strftime('%H:%M'),
                    'window_end': checkpoint.window_end.strftime('%H:%M'),
                    'is_required': checkpoint.is_required,
                    'order': checkpoint.order
                })
            
            return JsonResponse({
                'success': True,
                'checkpoints': checkpoints_data
            })
            
        except EventSession.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Session not found.'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'Error: {str(e)}'
            })


class CheckpointScanView(TemplateView):
    template_name = 'attendance/checkpoint_scan.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        checkpoint_code = kwargs.get('checkpoint_code')
        
        try:
            checkpoint = AttendanceCheckpoint.objects.get(
                checkpoint_code=checkpoint_code,
                is_active=True
            )
            context['checkpoint'] = checkpoint
            context['valid_checkpoint'] = True
            
            # Get the related event
            if checkpoint.event:
                context['event'] = checkpoint.event
            elif checkpoint.event_session:
                context['event'] = checkpoint.event_session.event
                context['event_session'] = checkpoint.event_session
                
        except AttendanceCheckpoint.DoesNotExist:
            context['valid_checkpoint'] = False
            context['error'] = 'Invalid checkpoint code.'
            
        return context


@method_decorator(csrf_exempt, name='dispatch')
class RecordCheckpointAttendanceView(View):
    def post(self, request):
        try:
            data = json.loads(request.body)
            checkpoint_code = data.get('checkpoint_code')
            attendee_id = data.get('attendee_id')
            device_info = data.get('device_info', {})
            location_data = data.get('location')  # GPS location data
            location_error = data.get('location_error')  # Location error if any
            
            # Validate checkpoint
            try:
                checkpoint = AttendanceCheckpoint.objects.get(
                    checkpoint_code=checkpoint_code,
                    is_active=True
                )
            except AttendanceCheckpoint.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid checkpoint code.'
                })
            
            # Validate attendee
            try:
                attendee = Attendee.objects.get(attendee_id=attendee_id, is_active=True)
            except Attendee.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid attendee ID.'
                })
            
            # Check if already attended
            existing_attendance = CheckpointAttendance.objects.filter(
                checkpoint=checkpoint,
                attendee=attendee
            ).first()
            
            if existing_attendance:
                return JsonResponse({
                    'success': False,
                    'error': 'Attendance already recorded for this checkpoint.'
                })
            
            # Get client IP
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip = x_forwarded_for.split(',')[0]
            else:
                ip = request.META.get('REMOTE_ADDR')
            
            # Prepare location fields
            latitude = None
            longitude = None
            location_accuracy = None
            location_timestamp = None
            
            if location_data:
                try:
                    latitude = Decimal(str(location_data.get('latitude')))
                    longitude = Decimal(str(location_data.get('longitude')))
                    location_accuracy = float(location_data.get('accuracy', 0))
                    if location_data.get('timestamp'):
                        from datetime import datetime
                        location_timestamp = datetime.fromisoformat(location_data['timestamp'].replace('Z', '+00:00'))
                except (ValueError, TypeError) as e:
                    location_error = f"Invalid location data: {str(e)}"
            
            # Create attendance record
            checkpoint_attendance = CheckpointAttendance.objects.create(
                checkpoint=checkpoint,
                attendee=attendee,
                event=checkpoint.event,
                event_session=checkpoint.event_session,
                device_fingerprint=str(device_info),
                ip_address=ip,
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                latitude=latitude,
                longitude=longitude,
                location_accuracy=location_accuracy,
                location_timestamp=location_timestamp
            )
            
            # Create device footprint
            DeviceFootprint.objects.create(
                checkpoint_attendance=checkpoint_attendance,
                screen_resolution=device_info.get('screen', ''),
                timezone=device_info.get('timezone', ''),
                language=device_info.get('language', ''),
                platform=device_info.get('platform', ''),
                browser_fingerprint=str(device_info)
            )
            
            # Determine status
            status = 'on_time'
            if checkpoint_attendance.is_late:
                status = 'late'
            elif not checkpoint_attendance.is_on_time and not checkpoint_attendance.is_late:
                status = 'early'
            
            return JsonResponse({
                'success': True,
                'message': 'Checkpoint attendance recorded successfully!',
                'attendee_name': attendee.name,
                'checkpoint_name': checkpoint.name,
                'status': status,
                'timestamp': checkpoint_attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                'location_captured': latitude is not None and longitude is not None,
                'location_error': location_error
            })
            
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON data.'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'Server error: {str(e)}'
            })


class ValidateAttendeeIDView(View):
    """API endpoint to validate attendee ID"""
    def post(self, request):
        try:
            data = json.loads(request.body)
            attendee_id = data.get('attendee_id')
            
            try:
                attendee = Attendee.objects.get(attendee_id=attendee_id, is_active=True)
                return JsonResponse({
                    'success': True,
                    'attendee_name': attendee.name,
                    'attendee_email': attendee.email
                })
            except Attendee.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid attendee ID.'
                })
                
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON data.'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'Server error: {str(e)}'
            })

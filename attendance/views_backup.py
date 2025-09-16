from django.shortcuts import render, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, TemplateView, View
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.utils import timezone
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
class RecordAttendanceView(View):
    def post(self, request):
        try:
            data = json.loads(request.body)
            qr_code = data.get('qr_code')
            attendee_id = data.get('attendee_id')
            device_info = data.get('device_info', {})
            
            # Validate event
            try:
                event = Event.objects.get(qr_code=qr_code, is_active=True)
            except Event.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid QR code or event not found.'
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
            if AttendanceRecord.objects.filter(event=event, attendee=attendee).exists():
                return JsonResponse({
                    'success': False,
                    'error': 'Attendance already recorded for this event.'
                })
            
            # Get client IP
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip = x_forwarded_for.split(',')[0]
            else:
                ip = request.META.get('REMOTE_ADDR')
            
            # Create attendance record
            attendance = AttendanceRecord.objects.create(
                event=event,
                attendee=attendee,
                device_fingerprint=json.dumps(device_info),
                ip_address=ip,
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            
            # Create device footprint
            DeviceFootprint.objects.create(
                attendance_record=attendance,
                screen_resolution=device_info.get('screen', ''),
                timezone=device_info.get('timezone', ''),
                language=device_info.get('language', ''),
                platform=device_info.get('platform', ''),
                browser_fingerprint=json.dumps(device_info)
            )
            
            return JsonResponse({
                'success': True,
                'message': f'Attendance recorded successfully for {attendee.full_name}',
                'attendee_name': attendee.full_name,
                'event_name': event.name,
                'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
            })
            
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON data.'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'An error occurred: {str(e)}'
            })


@method_decorator(csrf_exempt, name='dispatch')
class RecordUnifiedAttendanceView(View):
    """Record attendance for events with dynamic checkpoint selection"""
    def post(self, request):
        try:
            data = json.loads(request.body)
            qr_code = data.get('qr_code')
            attendee_id = data.get('attendee_id')
            checkpoint_id = data.get('checkpoint_id')  # Can be None for simple attendance
            target_date = data.get('target_date')  # Optional, defaults to today
            device_info = data.get('device_info', {})
            
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
            
            if checkpoint_id:
                # Record checkpoint attendance
                try:
                    checkpoint = AttendanceCheckpoint.objects.get(
                        id=checkpoint_id, is_active=True
                    )
                    
                    # Verify checkpoint belongs to this event
                    if checkpoint.event != event and (not checkpoint.event_session or checkpoint.event_session.event != event):
                        return JsonResponse({
                            'success': False,
                            'error': 'Checkpoint does not belong to this event.'
                        })
                    
                    # Check if checkpoint applies to this date
                    if not checkpoint.applies_to_date(target_date):
                        return JsonResponse({
                            'success': False,
                            'error': f'This checkpoint does not apply to {target_date}.'
                        })
                    
                    # Check for existing checkpoint attendance
                    existing_checkpoint = CheckpointAttendance.objects.filter(
                        checkpoint=checkpoint,
                        attendee=attendee,
                        timestamp__date=target_date
                    ).first()
                    
                    if existing_checkpoint:
                        return JsonResponse({
                            'success': False,
                            'error': 'Attendance already recorded for this checkpoint today.'
                        })
                    
                    # Create checkpoint attendance
                    attendance = CheckpointAttendance.objects.create(
                        checkpoint=checkpoint,
                        attendee=attendee,
                        event=checkpoint.event,
                        event_session=checkpoint.event_session,
                        device_fingerprint=json.dumps(device_info),
                        ip_address=ip,
                        user_agent=request.META.get('HTTP_USER_AGENT', '')
                    )
                    
                    # Create device footprint
                    DeviceFootprint.objects.create(
                        checkpoint_attendance=attendance,
                        screen_resolution=device_info.get('screen', ''),
                        timezone=device_info.get('timezone', ''),
                        language=device_info.get('language', ''),
                        platform=device_info.get('platform', ''),
                        browser_fingerprint=json.dumps(device_info)
                    )
                    
                    # Determine status
                    status_message = "on time"
                    if attendance.is_late:
                        status_message = "late"
                    elif not attendance.is_on_time and not attendance.is_late:
                        status_message = "early"
                    
                    return JsonResponse({
                        'success': True,
                        'message': f'Checkpoint attendance recorded successfully ({status_message})',
                        'attendee_name': attendee.full_name,
                        'event_name': event.name,
                        'checkpoint_name': checkpoint.name,
                        'status': status_message,
                        'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    })
                    
                except AttendanceCheckpoint.DoesNotExist:
                    return JsonResponse({
                        'success': False,
                        'error': 'Invalid checkpoint.'
                    })
            else:
                # Record general event attendance
                if event.event_type == 'single':
                    # Check for existing attendance
                    if AttendanceRecord.objects.filter(event=event, attendee=attendee).exists():
                        return JsonResponse({
                            'success': False,
                            'error': 'Attendance already recorded for this event.'
                        })
                    
                    # Create attendance record
                    attendance = AttendanceRecord.objects.create(
                        event=event,
                        attendee=attendee,
                        device_fingerprint=json.dumps(device_info),
                        ip_address=ip,
                        user_agent=request.META.get('HTTP_USER_AGENT', '')
                    )
                    
                    # Create device footprint
                    DeviceFootprint.objects.create(
                        attendance_record=attendance,
                        screen_resolution=device_info.get('screen', ''),
                        timezone=device_info.get('timezone', ''),
                        language=device_info.get('language', ''),
                        platform=device_info.get('platform', ''),
                        browser_fingerprint=json.dumps(device_info)
                    )
                    
                    return JsonResponse({
                        'success': True,
                        'message': f'Attendance recorded successfully for {attendee.full_name}',
                        'attendee_name': attendee.full_name,
                        'event_name': event.name,
                        'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    })
                else:
                    # For multi-day events, find the session for target date
                    try:
                        session = event.eventsession_set.get(session_date=target_date)
                        
                        # Check for existing session attendance
                        if SessionAttendance.objects.filter(event_session=session, attendee=attendee).exists():
                            return JsonResponse({
                                'success': False,
                                'error': 'Attendance already recorded for this session.'
                            })
                        
                        # Create session attendance
                        attendance = SessionAttendance.objects.create(
                            event_session=session,
                            attendee=attendee,
                            device_fingerprint=json.dumps(device_info),
                            ip_address=ip,
                            user_agent=request.META.get('HTTP_USER_AGENT', '')
                        )
                        
                        # Create device footprint
                        DeviceFootprint.objects.create(
                            session_attendance=attendance,
                            screen_resolution=device_info.get('screen', ''),
                            timezone=device_info.get('timezone', ''),
                            language=device_info.get('language', ''),
                            platform=device_info.get('platform', ''),
                            browser_fingerprint=json.dumps(device_info)
                        )
                        
                        return JsonResponse({
                            'success': True,
                            'message': f'Session attendance recorded successfully for {attendee.full_name}',
                            'attendee_name': attendee.full_name,
                            'event_name': event.name,
                            'session_info': f'Session {session.session_number} - {session.session_date}',
                            'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                        })
                        
                    except:
                        return JsonResponse({
                            'success': False,
                            'error': f'No session found for {target_date}.'
                        })
            
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON data.'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'An error occurred: {str(e)}'
            })


class CheckpointScanView(TemplateView):
    template_name = 'attendance/checkpoint_scan.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        checkpoint_code = kwargs.get('checkpoint_code')
        
        try:
            checkpoint = AttendanceCheckpoint.objects.select_related('event', 'event_session').get(
                checkpoint_code=checkpoint_code, is_active=True
            )
            context['checkpoint'] = checkpoint
            context['event'] = checkpoint.event or checkpoint.event_session.event
            context['event_session'] = checkpoint.event_session
            context['valid_qr'] = True
            
            # Get current time to show if checkpoint is active
            from django.utils import timezone
            current_time = timezone.now().time()
            context['is_within_window'] = checkpoint.is_within_window(current_time)
            context['window_start'] = checkpoint.window_start
            context['window_end'] = checkpoint.window_end
            
        except AttendanceCheckpoint.DoesNotExist:
            context['valid_qr'] = False
            context['error'] = 'Invalid checkpoint QR code.'
        
        return context


@method_decorator(csrf_exempt, name='dispatch')
class RecordCheckpointAttendanceView(View):
    def post(self, request):
        try:
            data = json.loads(request.body)
            checkpoint_code = data.get('checkpoint_code')
            attendee_id = data.get('attendee_id')
            device_info = data.get('device_info', {})
            
            # Validate checkpoint
            try:
                checkpoint = AttendanceCheckpoint.objects.select_related('event', 'event_session').get(
                    checkpoint_code=checkpoint_code, is_active=True
                )
            except AttendanceCheckpoint.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid checkpoint QR code.'
                })
            
            # Validate attendee
            try:
                attendee = Attendee.objects.get(attendee_id=attendee_id, is_active=True)
            except Attendee.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid attendee ID.'
                })
            
            # Check if already attended this checkpoint
            existing_attendance = None
            if checkpoint.event:
                existing_attendance = CheckpointAttendance.objects.filter(
                    checkpoint=checkpoint, attendee=attendee, event=checkpoint.event
                ).first()
            elif checkpoint.event_session:
                existing_attendance = CheckpointAttendance.objects.filter(
                    checkpoint=checkpoint, attendee=attendee, event_session=checkpoint.event_session
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
            
            # Create checkpoint attendance record
            attendance = CheckpointAttendance.objects.create(
                checkpoint=checkpoint,
                attendee=attendee,
                event=checkpoint.event,
                event_session=checkpoint.event_session,
                device_fingerprint=json.dumps(device_info),
                ip_address=ip,
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            
            # Create device footprint
            DeviceFootprint.objects.create(
                checkpoint_attendance=attendance,
                screen_resolution=device_info.get('screen', ''),
                timezone=device_info.get('timezone', ''),
                language=device_info.get('language', ''),
                platform=device_info.get('platform', ''),
                browser_fingerprint=json.dumps(device_info)
            )
            
            # Determine status message
            status_message = "on time"
            if attendance.is_late:
                status_message = "late"
            elif not attendance.is_on_time and not attendance.is_late:
                status_message = "early"
            
            event_name = checkpoint.event.name if checkpoint.event else checkpoint.event_session.event.name
            
            return JsonResponse({
                'success': True,
                'message': f'Checkpoint attendance recorded successfully ({status_message})',
                'attendee_name': attendee.full_name,
                'event_name': event_name,
                'checkpoint_name': checkpoint.name,
                'checkpoint_time': checkpoint.required_time.strftime('%H:%M'),
                'status': status_message,
                'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
            })
            
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON data.'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'An error occurred: {str(e)}'
            })


@method_decorator(csrf_exempt, name='dispatch')
class RecordUnifiedAttendanceView(View):
    """Record attendance for events with dynamic checkpoint selection"""
    def post(self, request):
        try:
            data = json.loads(request.body)
            qr_code = data.get('qr_code')
            attendee_id = data.get('attendee_id')
            checkpoint_id = data.get('checkpoint_id')  # Can be None for simple attendance
            target_date = data.get('target_date')  # Optional, defaults to today
            device_info = data.get('device_info', {})
            
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
            
            if checkpoint_id:
                # Record checkpoint attendance
                try:
                    checkpoint = AttendanceCheckpoint.objects.get(
                        id=checkpoint_id, is_active=True
                    )
                    
                    # Verify checkpoint belongs to this event
                    if checkpoint.event != event and (not checkpoint.event_session or checkpoint.event_session.event != event):
                        return JsonResponse({
                            'success': False,
                            'error': 'Checkpoint does not belong to this event.'
                        })
                    
                    # Check if checkpoint applies to this date
                    if not checkpoint.applies_to_date(target_date):
                        return JsonResponse({
                            'success': False,
                            'error': f'This checkpoint does not apply to {target_date}.'
                        })
                    
                    # Check for existing checkpoint attendance
                    existing_checkpoint = CheckpointAttendance.objects.filter(
                        checkpoint=checkpoint,
                        attendee=attendee,
                        timestamp__date=target_date
                    ).first()
                    
                    if existing_checkpoint:
                        return JsonResponse({
                            'success': False,
                            'error': 'Attendance already recorded for this checkpoint today.'
                        })
                    
                    # Create checkpoint attendance
                    attendance = CheckpointAttendance.objects.create(
                        checkpoint=checkpoint,
                        attendee=attendee,
                        event=checkpoint.event,
                        event_session=checkpoint.event_session,
                        device_fingerprint=json.dumps(device_info),
                        ip_address=ip,
                        user_agent=request.META.get('HTTP_USER_AGENT', '')
                    )
                    
                    # Create device footprint
                    DeviceFootprint.objects.create(
                        checkpoint_attendance=attendance,
                        screen_resolution=device_info.get('screen', ''),
                        timezone=device_info.get('timezone', ''),
                        language=device_info.get('language', ''),
                        platform=device_info.get('platform', ''),
                        browser_fingerprint=json.dumps(device_info)
                    )
                    
                    # Determine status
                    status_message = "on time"
                    if attendance.is_late:
                        status_message = "late"
                    elif not attendance.is_on_time and not attendance.is_late:
                        status_message = "early"
                    
                    return JsonResponse({
                        'success': True,
                        'message': f'Checkpoint attendance recorded successfully ({status_message})',
                        'attendee_name': attendee.full_name,
                        'event_name': event.name,
                        'checkpoint_name': checkpoint.name,
                        'status': status_message,
                        'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    })
                    
                except AttendanceCheckpoint.DoesNotExist:
                    return JsonResponse({
                        'success': False,
                        'error': 'Invalid checkpoint.'
                    })
            else:
                # Record general event attendance
                if event.event_type == 'single':
                    # Check for existing attendance
                    if AttendanceRecord.objects.filter(event=event, attendee=attendee).exists():
                        return JsonResponse({
                            'success': False,
                            'error': 'Attendance already recorded for this event.'
                        })
                    
                    # Create attendance record
                    attendance = AttendanceRecord.objects.create(
                        event=event,
                        attendee=attendee,
                        device_fingerprint=json.dumps(device_info),
                        ip_address=ip,
                        user_agent=request.META.get('HTTP_USER_AGENT', '')
                    )
                    
                    # Create device footprint
                    DeviceFootprint.objects.create(
                        attendance_record=attendance,
                        screen_resolution=device_info.get('screen', ''),
                        timezone=device_info.get('timezone', ''),
                        language=device_info.get('language', ''),
                        platform=device_info.get('platform', ''),
                        browser_fingerprint=json.dumps(device_info)
                    )
                    
                    return JsonResponse({
                        'success': True,
                        'message': f'Attendance recorded successfully for {attendee.full_name}',
                        'attendee_name': attendee.full_name,
                        'event_name': event.name,
                        'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    })
                else:
                    # For multi-day events, find the session for target date
                    try:
                        session = event.eventsession_set.get(session_date=target_date)
                        
                        # Check for existing session attendance
                        if SessionAttendance.objects.filter(event_session=session, attendee=attendee).exists():
                            return JsonResponse({
                                'success': False,
                                'error': 'Attendance already recorded for this session.'
                            })
                        
                        # Create session attendance
                        attendance = SessionAttendance.objects.create(
                            event_session=session,
                            attendee=attendee,
                            device_fingerprint=json.dumps(device_info),
                            ip_address=ip,
                            user_agent=request.META.get('HTTP_USER_AGENT', '')
                        )
                        
                        # Create device footprint
                        DeviceFootprint.objects.create(
                            session_attendance=attendance,
                            screen_resolution=device_info.get('screen', ''),
                            timezone=device_info.get('timezone', ''),
                            language=device_info.get('language', ''),
                            platform=device_info.get('platform', ''),
                            browser_fingerprint=json.dumps(device_info)
                        )
                        
                        return JsonResponse({
                            'success': True,
                            'message': f'Session attendance recorded successfully for {attendee.full_name}',
                            'attendee_name': attendee.full_name,
                            'event_name': event.name,
                            'session_info': f'Session {session.session_number} - {session.session_date}',
                            'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                        })
                        
                    except:
                        return JsonResponse({
                            'success': False,
                            'error': f'No session found for {target_date}.'
                        })
            
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON data.'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'An error occurred: {str(e)}'
            })


@method_decorator(csrf_exempt, name='dispatch')
class GetEventCheckpointsView(View):
    def get(self, request, event_id):
        try:
            event = Event.objects.get(pk=event_id)
            checkpoints = AttendanceCheckpoint.objects.filter(
                event=event, is_active=True
            ).order_by('order')
            
            checkpoint_data = []
            for checkpoint in checkpoints:
                checkpoint_data.append({
                    'id': checkpoint.id,
                    'name': checkpoint.name,
                    'checkpoint_type': checkpoint.checkpoint_type,
                    'required_time': checkpoint.required_time.strftime('%H:%M'),
                    'window_start': checkpoint.window_start.strftime('%H:%M'),
                    'window_end': checkpoint.window_end.strftime('%H:%M'),
                    'order': checkpoint.order,
                    'checkpoint_code': checkpoint.checkpoint_code
                })
            
            return JsonResponse({
                'success': True,
                'checkpoints': checkpoint_data
            })
            
        except Event.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Event not found.'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'An error occurred: {str(e)}'
            })


@method_decorator(csrf_exempt, name='dispatch')
class RecordUnifiedAttendanceView(View):
    """Record attendance for events with dynamic checkpoint selection"""
    def post(self, request):
        try:
            data = json.loads(request.body)
            qr_code = data.get('qr_code')
            attendee_id = data.get('attendee_id')
            checkpoint_id = data.get('checkpoint_id')  # Can be None for simple attendance
            target_date = data.get('target_date')  # Optional, defaults to today
            device_info = data.get('device_info', {})
            
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
            
            if checkpoint_id:
                # Record checkpoint attendance
                try:
                    checkpoint = AttendanceCheckpoint.objects.get(
                        id=checkpoint_id, is_active=True
                    )
                    
                    # Verify checkpoint belongs to this event
                    if checkpoint.event != event and (not checkpoint.event_session or checkpoint.event_session.event != event):
                        return JsonResponse({
                            'success': False,
                            'error': 'Checkpoint does not belong to this event.'
                        })
                    
                    # Check if checkpoint applies to this date
                    if not checkpoint.applies_to_date(target_date):
                        return JsonResponse({
                            'success': False,
                            'error': f'This checkpoint does not apply to {target_date}.'
                        })
                    
                    # Check for existing checkpoint attendance
                    existing_checkpoint = CheckpointAttendance.objects.filter(
                        checkpoint=checkpoint,
                        attendee=attendee,
                        timestamp__date=target_date
                    ).first()
                    
                    if existing_checkpoint:
                        return JsonResponse({
                            'success': False,
                            'error': 'Attendance already recorded for this checkpoint today.'
                        })
                    
                    # Create checkpoint attendance
                    attendance = CheckpointAttendance.objects.create(
                        checkpoint=checkpoint,
                        attendee=attendee,
                        event=checkpoint.event,
                        event_session=checkpoint.event_session,
                        device_fingerprint=json.dumps(device_info),
                        ip_address=ip,
                        user_agent=request.META.get('HTTP_USER_AGENT', '')
                    )
                    
                    # Create device footprint
                    DeviceFootprint.objects.create(
                        checkpoint_attendance=attendance,
                        screen_resolution=device_info.get('screen', ''),
                        timezone=device_info.get('timezone', ''),
                        language=device_info.get('language', ''),
                        platform=device_info.get('platform', ''),
                        browser_fingerprint=json.dumps(device_info)
                    )
                    
                    # Determine status
                    status_message = "on time"
                    if attendance.is_late:
                        status_message = "late"
                    elif not attendance.is_on_time and not attendance.is_late:
                        status_message = "early"
                    
                    return JsonResponse({
                        'success': True,
                        'message': f'Checkpoint attendance recorded successfully ({status_message})',
                        'attendee_name': attendee.full_name,
                        'event_name': event.name,
                        'checkpoint_name': checkpoint.name,
                        'status': status_message,
                        'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    })
                    
                except AttendanceCheckpoint.DoesNotExist:
                    return JsonResponse({
                        'success': False,
                        'error': 'Invalid checkpoint.'
                    })
            else:
                # Record general event attendance
                if event.event_type == 'single':
                    # Check for existing attendance
                    if AttendanceRecord.objects.filter(event=event, attendee=attendee).exists():
                        return JsonResponse({
                            'success': False,
                            'error': 'Attendance already recorded for this event.'
                        })
                    
                    # Create attendance record
                    attendance = AttendanceRecord.objects.create(
                        event=event,
                        attendee=attendee,
                        device_fingerprint=json.dumps(device_info),
                        ip_address=ip,
                        user_agent=request.META.get('HTTP_USER_AGENT', '')
                    )
                    
                    # Create device footprint
                    DeviceFootprint.objects.create(
                        attendance_record=attendance,
                        screen_resolution=device_info.get('screen', ''),
                        timezone=device_info.get('timezone', ''),
                        language=device_info.get('language', ''),
                        platform=device_info.get('platform', ''),
                        browser_fingerprint=json.dumps(device_info)
                    )
                    
                    return JsonResponse({
                        'success': True,
                        'message': f'Attendance recorded successfully for {attendee.full_name}',
                        'attendee_name': attendee.full_name,
                        'event_name': event.name,
                        'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    })
                else:
                    # For multi-day events, find the session for target date
                    try:
                        session = event.eventsession_set.get(session_date=target_date)
                        
                        # Check for existing session attendance
                        if SessionAttendance.objects.filter(event_session=session, attendee=attendee).exists():
                            return JsonResponse({
                                'success': False,
                                'error': 'Attendance already recorded for this session.'
                            })
                        
                        # Create session attendance
                        attendance = SessionAttendance.objects.create(
                            event_session=session,
                            attendee=attendee,
                            device_fingerprint=json.dumps(device_info),
                            ip_address=ip,
                            user_agent=request.META.get('HTTP_USER_AGENT', '')
                        )
                        
                        # Create device footprint
                        DeviceFootprint.objects.create(
                            session_attendance=attendance,
                            screen_resolution=device_info.get('screen', ''),
                            timezone=device_info.get('timezone', ''),
                            language=device_info.get('language', ''),
                            platform=device_info.get('platform', ''),
                            browser_fingerprint=json.dumps(device_info)
                        )
                        
                        return JsonResponse({
                            'success': True,
                            'message': f'Session attendance recorded successfully for {attendee.full_name}',
                            'attendee_name': attendee.full_name,
                            'event_name': event.name,
                            'session_info': f'Session {session.session_number} - {session.session_date}',
                            'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                        })
                        
                    except:
                        return JsonResponse({
                            'success': False,
                            'error': f'No session found for {target_date}.'
                        })
            
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON data.'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'An error occurred: {str(e)}'
            })


@method_decorator(csrf_exempt, name='dispatch')
class GetSessionCheckpointsView(View):
    def get(self, request, session_id):
        try:
            session = EventSession.objects.get(pk=session_id)
            checkpoints = AttendanceCheckpoint.objects.filter(
                event_session=session, is_active=True
            ).order_by('order')
            
            checkpoint_data = []
            for checkpoint in checkpoints:
                checkpoint_data.append({
                    'id': checkpoint.id,
                    'name': checkpoint.name,
                    'checkpoint_type': checkpoint.checkpoint_type,
                    'required_time': checkpoint.required_time.strftime('%H:%M'),
                    'window_start': checkpoint.window_start.strftime('%H:%M'),
                    'window_end': checkpoint.window_end.strftime('%H:%M'),
                    'order': checkpoint.order,
                    'checkpoint_code': checkpoint.checkpoint_code
                })
            
            return JsonResponse({
                'success': True,
                'checkpoints': checkpoint_data
            })
            
        except EventSession.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Session not found.'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'An error occurred: {str(e)}'
            })


@method_decorator(csrf_exempt, name='dispatch')
class RecordUnifiedAttendanceView(View):
    """Record attendance for events with dynamic checkpoint selection"""
    def post(self, request):
        try:
            data = json.loads(request.body)
            qr_code = data.get('qr_code')
            attendee_id = data.get('attendee_id')
            checkpoint_id = data.get('checkpoint_id')  # Can be None for simple attendance
            target_date = data.get('target_date')  # Optional, defaults to today
            device_info = data.get('device_info', {})
            
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
            
            if checkpoint_id:
                # Record checkpoint attendance
                try:
                    checkpoint = AttendanceCheckpoint.objects.get(
                        id=checkpoint_id, is_active=True
                    )
                    
                    # Verify checkpoint belongs to this event
                    if checkpoint.event != event and (not checkpoint.event_session or checkpoint.event_session.event != event):
                        return JsonResponse({
                            'success': False,
                            'error': 'Checkpoint does not belong to this event.'
                        })
                    
                    # Check if checkpoint applies to this date
                    if not checkpoint.applies_to_date(target_date):
                        return JsonResponse({
                            'success': False,
                            'error': f'This checkpoint does not apply to {target_date}.'
                        })
                    
                    # Check for existing checkpoint attendance
                    existing_checkpoint = CheckpointAttendance.objects.filter(
                        checkpoint=checkpoint,
                        attendee=attendee,
                        timestamp__date=target_date
                    ).first()
                    
                    if existing_checkpoint:
                        return JsonResponse({
                            'success': False,
                            'error': 'Attendance already recorded for this checkpoint today.'
                        })
                    
                    # Create checkpoint attendance
                    attendance = CheckpointAttendance.objects.create(
                        checkpoint=checkpoint,
                        attendee=attendee,
                        event=checkpoint.event,
                        event_session=checkpoint.event_session,
                        device_fingerprint=json.dumps(device_info),
                        ip_address=ip,
                        user_agent=request.META.get('HTTP_USER_AGENT', '')
                    )
                    
                    # Create device footprint
                    DeviceFootprint.objects.create(
                        checkpoint_attendance=attendance,
                        screen_resolution=device_info.get('screen', ''),
                        timezone=device_info.get('timezone', ''),
                        language=device_info.get('language', ''),
                        platform=device_info.get('platform', ''),
                        browser_fingerprint=json.dumps(device_info)
                    )
                    
                    # Determine status
                    status_message = "on time"
                    if attendance.is_late:
                        status_message = "late"
                    elif not attendance.is_on_time and not attendance.is_late:
                        status_message = "early"
                    
                    return JsonResponse({
                        'success': True,
                        'message': f'Checkpoint attendance recorded successfully ({status_message})',
                        'attendee_name': attendee.full_name,
                        'event_name': event.name,
                        'checkpoint_name': checkpoint.name,
                        'status': status_message,
                        'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    })
                    
                except AttendanceCheckpoint.DoesNotExist:
                    return JsonResponse({
                        'success': False,
                        'error': 'Invalid checkpoint.'
                    })
            else:
                # Record general event attendance
                if event.event_type == 'single':
                    # Check for existing attendance
                    if AttendanceRecord.objects.filter(event=event, attendee=attendee).exists():
                        return JsonResponse({
                            'success': False,
                            'error': 'Attendance already recorded for this event.'
                        })
                    
                    # Create attendance record
                    attendance = AttendanceRecord.objects.create(
                        event=event,
                        attendee=attendee,
                        device_fingerprint=json.dumps(device_info),
                        ip_address=ip,
                        user_agent=request.META.get('HTTP_USER_AGENT', '')
                    )
                    
                    # Create device footprint
                    DeviceFootprint.objects.create(
                        attendance_record=attendance,
                        screen_resolution=device_info.get('screen', ''),
                        timezone=device_info.get('timezone', ''),
                        language=device_info.get('language', ''),
                        platform=device_info.get('platform', ''),
                        browser_fingerprint=json.dumps(device_info)
                    )
                    
                    return JsonResponse({
                        'success': True,
                        'message': f'Attendance recorded successfully for {attendee.full_name}',
                        'attendee_name': attendee.full_name,
                        'event_name': event.name,
                        'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    })
                else:
                    # For multi-day events, find the session for target date
                    try:
                        session = event.eventsession_set.get(session_date=target_date)
                        
                        # Check for existing session attendance
                        if SessionAttendance.objects.filter(event_session=session, attendee=attendee).exists():
                            return JsonResponse({
                                'success': False,
                                'error': 'Attendance already recorded for this session.'
                            })
                        
                        # Create session attendance
                        attendance = SessionAttendance.objects.create(
                            event_session=session,
                            attendee=attendee,
                            device_fingerprint=json.dumps(device_info),
                            ip_address=ip,
                            user_agent=request.META.get('HTTP_USER_AGENT', '')
                        )
                        
                        # Create device footprint
                        DeviceFootprint.objects.create(
                            session_attendance=attendance,
                            screen_resolution=device_info.get('screen', ''),
                            timezone=device_info.get('timezone', ''),
                            language=device_info.get('language', ''),
                            platform=device_info.get('platform', ''),
                            browser_fingerprint=json.dumps(device_info)
                        )
                        
                        return JsonResponse({
                            'success': True,
                            'message': f'Session attendance recorded successfully for {attendee.full_name}',
                            'attendee_name': attendee.full_name,
                            'event_name': event.name,
                            'session_info': f'Session {session.session_number} - {session.session_date}',
                            'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                        })
                        
                    except:
                        return JsonResponse({
                            'success': False,
                            'error': f'No session found for {target_date}.'
                        })
            
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON data.'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'An error occurred: {str(e)}'
            })


class SessionScanView(TemplateView):
    template_name = 'attendance/session_scan.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qr_code = kwargs.get('qr_code')
        
        try:
            session = EventSession.objects.get(qr_code=qr_code, is_active=True)
            context['session'] = session
            context['event'] = session.event
            context['valid_qr'] = True
        except EventSession.DoesNotExist:
            context['valid_qr'] = False
            context['error'] = 'Invalid QR code or session not found.'
        
        return context


@method_decorator(csrf_exempt, name='dispatch')
class RecordSessionAttendanceView(View):
    def post(self, request):
        try:
            data = json.loads(request.body)
            qr_code = data.get('qr_code')
            attendee_id = data.get('attendee_id')
            device_info = data.get('device_info', {})
            
            # Validate session
            try:
                session = EventSession.objects.get(qr_code=qr_code, is_active=True)
            except EventSession.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid QR code or session not found.'
                })
            
            # Validate attendee
            try:
                attendee = Attendee.objects.get(attendee_id=attendee_id, is_active=True)
            except Attendee.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid attendee ID.'
                })
            
            # Check if already attended this session
            if SessionAttendance.objects.filter(event_session=session, attendee=attendee).exists():
                return JsonResponse({
                    'success': False,
                    'error': 'Attendance already recorded for this session.'
                })
            
            # Get client IP
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip = x_forwarded_for.split(',')[0]
            else:
                ip = request.META.get('REMOTE_ADDR')
            
            # Create session attendance record
            attendance = SessionAttendance.objects.create(
                event_session=session,
                attendee=attendee,
                device_fingerprint=json.dumps(device_info),
                ip_address=ip,
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            
            # Create device footprint
            DeviceFootprint.objects.create(
                session_attendance=attendance,
                screen_resolution=device_info.get('screen', ''),
                timezone=device_info.get('timezone', ''),
                language=device_info.get('language', ''),
                platform=device_info.get('platform', ''),
                browser_fingerprint=json.dumps(device_info)
            )
            
            return JsonResponse({
                'success': True,
                'message': f'Attendance recorded successfully for {attendee.full_name}',
                'attendee_name': attendee.full_name,
                'event_name': session.event.name,
                'session_info': f'Session {session.session_number} - {session.session_date}',
                'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
            })
            
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON data.'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'An error occurred: {str(e)}'
            })


@method_decorator(csrf_exempt, name='dispatch')
class RecordUnifiedAttendanceView(View):
    """Record attendance for events with dynamic checkpoint selection"""
    def post(self, request):
        try:
            data = json.loads(request.body)
            qr_code = data.get('qr_code')
            attendee_id = data.get('attendee_id')
            checkpoint_id = data.get('checkpoint_id')  # Can be None for simple attendance
            target_date = data.get('target_date')  # Optional, defaults to today
            device_info = data.get('device_info', {})
            
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
            
            if checkpoint_id:
                # Record checkpoint attendance
                try:
                    checkpoint = AttendanceCheckpoint.objects.get(
                        id=checkpoint_id, is_active=True
                    )
                    
                    # Verify checkpoint belongs to this event
                    if checkpoint.event != event and (not checkpoint.event_session or checkpoint.event_session.event != event):
                        return JsonResponse({
                            'success': False,
                            'error': 'Checkpoint does not belong to this event.'
                        })
                    
                    # Check if checkpoint applies to this date
                    if not checkpoint.applies_to_date(target_date):
                        return JsonResponse({
                            'success': False,
                            'error': f'This checkpoint does not apply to {target_date}.'
                        })
                    
                    # Check for existing checkpoint attendance
                    existing_checkpoint = CheckpointAttendance.objects.filter(
                        checkpoint=checkpoint,
                        attendee=attendee,
                        timestamp__date=target_date
                    ).first()
                    
                    if existing_checkpoint:
                        return JsonResponse({
                            'success': False,
                            'error': 'Attendance already recorded for this checkpoint today.'
                        })
                    
                    # Create checkpoint attendance
                    attendance = CheckpointAttendance.objects.create(
                        checkpoint=checkpoint,
                        attendee=attendee,
                        event=checkpoint.event,
                        event_session=checkpoint.event_session,
                        device_fingerprint=json.dumps(device_info),
                        ip_address=ip,
                        user_agent=request.META.get('HTTP_USER_AGENT', '')
                    )
                    
                    # Create device footprint
                    DeviceFootprint.objects.create(
                        checkpoint_attendance=attendance,
                        screen_resolution=device_info.get('screen', ''),
                        timezone=device_info.get('timezone', ''),
                        language=device_info.get('language', ''),
                        platform=device_info.get('platform', ''),
                        browser_fingerprint=json.dumps(device_info)
                    )
                    
                    # Determine status
                    status_message = "on time"
                    if attendance.is_late:
                        status_message = "late"
                    elif not attendance.is_on_time and not attendance.is_late:
                        status_message = "early"
                    
                    return JsonResponse({
                        'success': True,
                        'message': f'Checkpoint attendance recorded successfully ({status_message})',
                        'attendee_name': attendee.full_name,
                        'event_name': event.name,
                        'checkpoint_name': checkpoint.name,
                        'status': status_message,
                        'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    })
                    
                except AttendanceCheckpoint.DoesNotExist:
                    return JsonResponse({
                        'success': False,
                        'error': 'Invalid checkpoint.'
                    })
            else:
                # Record general event attendance
                if event.event_type == 'single':
                    # Check for existing attendance
                    if AttendanceRecord.objects.filter(event=event, attendee=attendee).exists():
                        return JsonResponse({
                            'success': False,
                            'error': 'Attendance already recorded for this event.'
                        })
                    
                    # Create attendance record
                    attendance = AttendanceRecord.objects.create(
                        event=event,
                        attendee=attendee,
                        device_fingerprint=json.dumps(device_info),
                        ip_address=ip,
                        user_agent=request.META.get('HTTP_USER_AGENT', '')
                    )
                    
                    # Create device footprint
                    DeviceFootprint.objects.create(
                        attendance_record=attendance,
                        screen_resolution=device_info.get('screen', ''),
                        timezone=device_info.get('timezone', ''),
                        language=device_info.get('language', ''),
                        platform=device_info.get('platform', ''),
                        browser_fingerprint=json.dumps(device_info)
                    )
                    
                    return JsonResponse({
                        'success': True,
                        'message': f'Attendance recorded successfully for {attendee.full_name}',
                        'attendee_name': attendee.full_name,
                        'event_name': event.name,
                        'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    })
                else:
                    # For multi-day events, find the session for target date
                    try:
                        session = event.eventsession_set.get(session_date=target_date)
                        
                        # Check for existing session attendance
                        if SessionAttendance.objects.filter(event_session=session, attendee=attendee).exists():
                            return JsonResponse({
                                'success': False,
                                'error': 'Attendance already recorded for this session.'
                            })
                        
                        # Create session attendance
                        attendance = SessionAttendance.objects.create(
                            event_session=session,
                            attendee=attendee,
                            device_fingerprint=json.dumps(device_info),
                            ip_address=ip,
                            user_agent=request.META.get('HTTP_USER_AGENT', '')
                        )
                        
                        # Create device footprint
                        DeviceFootprint.objects.create(
                            session_attendance=attendance,
                            screen_resolution=device_info.get('screen', ''),
                            timezone=device_info.get('timezone', ''),
                            language=device_info.get('language', ''),
                            platform=device_info.get('platform', ''),
                            browser_fingerprint=json.dumps(device_info)
                        )
                        
                        return JsonResponse({
                            'success': True,
                            'message': f'Session attendance recorded successfully for {attendee.full_name}',
                            'attendee_name': attendee.full_name,
                            'event_name': event.name,
                            'session_info': f'Session {session.session_number} - {session.session_date}',
                            'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                        })
                        
                    except:
                        return JsonResponse({
                            'success': False,
                            'error': f'No session found for {target_date}.'
                        })
            
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON data.'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'An error occurred: {str(e)}'
            })


class CheckpointScanView(TemplateView):
    template_name = 'attendance/checkpoint_scan.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        checkpoint_code = kwargs.get('checkpoint_code')
        
        try:
            checkpoint = AttendanceCheckpoint.objects.select_related('event', 'event_session').get(
                checkpoint_code=checkpoint_code, is_active=True
            )
            context['checkpoint'] = checkpoint
            context['event'] = checkpoint.event or checkpoint.event_session.event
            context['event_session'] = checkpoint.event_session
            context['valid_qr'] = True
            
            # Get current time to show if checkpoint is active
            from django.utils import timezone
            current_time = timezone.now().time()
            context['is_within_window'] = checkpoint.is_within_window(current_time)
            context['window_start'] = checkpoint.window_start
            context['window_end'] = checkpoint.window_end
            
        except AttendanceCheckpoint.DoesNotExist:
            context['valid_qr'] = False
            context['error'] = 'Invalid checkpoint QR code.'
        
        return context


@method_decorator(csrf_exempt, name='dispatch')
class RecordCheckpointAttendanceView(View):
    def post(self, request):
        try:
            data = json.loads(request.body)
            checkpoint_code = data.get('checkpoint_code')
            attendee_id = data.get('attendee_id')
            device_info = data.get('device_info', {})
            
            # Validate checkpoint
            try:
                checkpoint = AttendanceCheckpoint.objects.select_related('event', 'event_session').get(
                    checkpoint_code=checkpoint_code, is_active=True
                )
            except AttendanceCheckpoint.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid checkpoint QR code.'
                })
            
            # Validate attendee
            try:
                attendee = Attendee.objects.get(attendee_id=attendee_id, is_active=True)
            except Attendee.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid attendee ID.'
                })
            
            # Check if already attended this checkpoint
            existing_attendance = None
            if checkpoint.event:
                existing_attendance = CheckpointAttendance.objects.filter(
                    checkpoint=checkpoint, attendee=attendee, event=checkpoint.event
                ).first()
            elif checkpoint.event_session:
                existing_attendance = CheckpointAttendance.objects.filter(
                    checkpoint=checkpoint, attendee=attendee, event_session=checkpoint.event_session
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
            
            # Create checkpoint attendance record
            attendance = CheckpointAttendance.objects.create(
                checkpoint=checkpoint,
                attendee=attendee,
                event=checkpoint.event,
                event_session=checkpoint.event_session,
                device_fingerprint=json.dumps(device_info),
                ip_address=ip,
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            
            # Create device footprint
            DeviceFootprint.objects.create(
                checkpoint_attendance=attendance,
                screen_resolution=device_info.get('screen', ''),
                timezone=device_info.get('timezone', ''),
                language=device_info.get('language', ''),
                platform=device_info.get('platform', ''),
                browser_fingerprint=json.dumps(device_info)
            )
            
            # Determine status message
            status_message = "on time"
            if attendance.is_late:
                status_message = "late"
            elif not attendance.is_on_time and not attendance.is_late:
                status_message = "early"
            
            event_name = checkpoint.event.name if checkpoint.event else checkpoint.event_session.event.name
            
            return JsonResponse({
                'success': True,
                'message': f'Checkpoint attendance recorded successfully ({status_message})',
                'attendee_name': attendee.full_name,
                'event_name': event_name,
                'checkpoint_name': checkpoint.name,
                'checkpoint_time': checkpoint.required_time.strftime('%H:%M'),
                'status': status_message,
                'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
            })
            
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON data.'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'An error occurred: {str(e)}'
            })


@method_decorator(csrf_exempt, name='dispatch')
class RecordUnifiedAttendanceView(View):
    """Record attendance for events with dynamic checkpoint selection"""
    def post(self, request):
        try:
            data = json.loads(request.body)
            qr_code = data.get('qr_code')
            attendee_id = data.get('attendee_id')
            checkpoint_id = data.get('checkpoint_id')  # Can be None for simple attendance
            target_date = data.get('target_date')  # Optional, defaults to today
            device_info = data.get('device_info', {})
            
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
            
            if checkpoint_id:
                # Record checkpoint attendance
                try:
                    checkpoint = AttendanceCheckpoint.objects.get(
                        id=checkpoint_id, is_active=True
                    )
                    
                    # Verify checkpoint belongs to this event
                    if checkpoint.event != event and (not checkpoint.event_session or checkpoint.event_session.event != event):
                        return JsonResponse({
                            'success': False,
                            'error': 'Checkpoint does not belong to this event.'
                        })
                    
                    # Check if checkpoint applies to this date
                    if not checkpoint.applies_to_date(target_date):
                        return JsonResponse({
                            'success': False,
                            'error': f'This checkpoint does not apply to {target_date}.'
                        })
                    
                    # Check for existing checkpoint attendance
                    existing_checkpoint = CheckpointAttendance.objects.filter(
                        checkpoint=checkpoint,
                        attendee=attendee,
                        timestamp__date=target_date
                    ).first()
                    
                    if existing_checkpoint:
                        return JsonResponse({
                            'success': False,
                            'error': 'Attendance already recorded for this checkpoint today.'
                        })
                    
                    # Create checkpoint attendance
                    attendance = CheckpointAttendance.objects.create(
                        checkpoint=checkpoint,
                        attendee=attendee,
                        event=checkpoint.event,
                        event_session=checkpoint.event_session,
                        device_fingerprint=json.dumps(device_info),
                        ip_address=ip,
                        user_agent=request.META.get('HTTP_USER_AGENT', '')
                    )
                    
                    # Create device footprint
                    DeviceFootprint.objects.create(
                        checkpoint_attendance=attendance,
                        screen_resolution=device_info.get('screen', ''),
                        timezone=device_info.get('timezone', ''),
                        language=device_info.get('language', ''),
                        platform=device_info.get('platform', ''),
                        browser_fingerprint=json.dumps(device_info)
                    )
                    
                    # Determine status
                    status_message = "on time"
                    if attendance.is_late:
                        status_message = "late"
                    elif not attendance.is_on_time and not attendance.is_late:
                        status_message = "early"
                    
                    return JsonResponse({
                        'success': True,
                        'message': f'Checkpoint attendance recorded successfully ({status_message})',
                        'attendee_name': attendee.full_name,
                        'event_name': event.name,
                        'checkpoint_name': checkpoint.name,
                        'status': status_message,
                        'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    })
                    
                except AttendanceCheckpoint.DoesNotExist:
                    return JsonResponse({
                        'success': False,
                        'error': 'Invalid checkpoint.'
                    })
            else:
                # Record general event attendance
                if event.event_type == 'single':
                    # Check for existing attendance
                    if AttendanceRecord.objects.filter(event=event, attendee=attendee).exists():
                        return JsonResponse({
                            'success': False,
                            'error': 'Attendance already recorded for this event.'
                        })
                    
                    # Create attendance record
                    attendance = AttendanceRecord.objects.create(
                        event=event,
                        attendee=attendee,
                        device_fingerprint=json.dumps(device_info),
                        ip_address=ip,
                        user_agent=request.META.get('HTTP_USER_AGENT', '')
                    )
                    
                    # Create device footprint
                    DeviceFootprint.objects.create(
                        attendance_record=attendance,
                        screen_resolution=device_info.get('screen', ''),
                        timezone=device_info.get('timezone', ''),
                        language=device_info.get('language', ''),
                        platform=device_info.get('platform', ''),
                        browser_fingerprint=json.dumps(device_info)
                    )
                    
                    return JsonResponse({
                        'success': True,
                        'message': f'Attendance recorded successfully for {attendee.full_name}',
                        'attendee_name': attendee.full_name,
                        'event_name': event.name,
                        'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    })
                else:
                    # For multi-day events, find the session for target date
                    try:
                        session = event.eventsession_set.get(session_date=target_date)
                        
                        # Check for existing session attendance
                        if SessionAttendance.objects.filter(event_session=session, attendee=attendee).exists():
                            return JsonResponse({
                                'success': False,
                                'error': 'Attendance already recorded for this session.'
                            })
                        
                        # Create session attendance
                        attendance = SessionAttendance.objects.create(
                            event_session=session,
                            attendee=attendee,
                            device_fingerprint=json.dumps(device_info),
                            ip_address=ip,
                            user_agent=request.META.get('HTTP_USER_AGENT', '')
                        )
                        
                        # Create device footprint
                        DeviceFootprint.objects.create(
                            session_attendance=attendance,
                            screen_resolution=device_info.get('screen', ''),
                            timezone=device_info.get('timezone', ''),
                            language=device_info.get('language', ''),
                            platform=device_info.get('platform', ''),
                            browser_fingerprint=json.dumps(device_info)
                        )
                        
                        return JsonResponse({
                            'success': True,
                            'message': f'Session attendance recorded successfully for {attendee.full_name}',
                            'attendee_name': attendee.full_name,
                            'event_name': event.name,
                            'session_info': f'Session {session.session_number} - {session.session_date}',
                            'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                        })
                        
                    except:
                        return JsonResponse({
                            'success': False,
                            'error': f'No session found for {target_date}.'
                        })
            
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON data.'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'An error occurred: {str(e)}'
            })


@method_decorator(csrf_exempt, name='dispatch')
class GetEventCheckpointsView(View):
    def get(self, request, event_id):
        try:
            event = Event.objects.get(pk=event_id)
            checkpoints = AttendanceCheckpoint.objects.filter(
                event=event, is_active=True
            ).order_by('order')
            
            checkpoint_data = []
            for checkpoint in checkpoints:
                checkpoint_data.append({
                    'id': checkpoint.id,
                    'name': checkpoint.name,
                    'checkpoint_type': checkpoint.checkpoint_type,
                    'required_time': checkpoint.required_time.strftime('%H:%M'),
                    'window_start': checkpoint.window_start.strftime('%H:%M'),
                    'window_end': checkpoint.window_end.strftime('%H:%M'),
                    'order': checkpoint.order,
                    'checkpoint_code': checkpoint.checkpoint_code
                })
            
            return JsonResponse({
                'success': True,
                'checkpoints': checkpoint_data
            })
            
        except Event.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Event not found.'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'An error occurred: {str(e)}'
            })


@method_decorator(csrf_exempt, name='dispatch')
class RecordUnifiedAttendanceView(View):
    """Record attendance for events with dynamic checkpoint selection"""
    def post(self, request):
        try:
            data = json.loads(request.body)
            qr_code = data.get('qr_code')
            attendee_id = data.get('attendee_id')
            checkpoint_id = data.get('checkpoint_id')  # Can be None for simple attendance
            target_date = data.get('target_date')  # Optional, defaults to today
            device_info = data.get('device_info', {})
            
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
            
            if checkpoint_id:
                # Record checkpoint attendance
                try:
                    checkpoint = AttendanceCheckpoint.objects.get(
                        id=checkpoint_id, is_active=True
                    )
                    
                    # Verify checkpoint belongs to this event
                    if checkpoint.event != event and (not checkpoint.event_session or checkpoint.event_session.event != event):
                        return JsonResponse({
                            'success': False,
                            'error': 'Checkpoint does not belong to this event.'
                        })
                    
                    # Check if checkpoint applies to this date
                    if not checkpoint.applies_to_date(target_date):
                        return JsonResponse({
                            'success': False,
                            'error': f'This checkpoint does not apply to {target_date}.'
                        })
                    
                    # Check for existing checkpoint attendance
                    existing_checkpoint = CheckpointAttendance.objects.filter(
                        checkpoint=checkpoint,
                        attendee=attendee,
                        timestamp__date=target_date
                    ).first()
                    
                    if existing_checkpoint:
                        return JsonResponse({
                            'success': False,
                            'error': 'Attendance already recorded for this checkpoint today.'
                        })
                    
                    # Create checkpoint attendance
                    attendance = CheckpointAttendance.objects.create(
                        checkpoint=checkpoint,
                        attendee=attendee,
                        event=checkpoint.event,
                        event_session=checkpoint.event_session,
                        device_fingerprint=json.dumps(device_info),
                        ip_address=ip,
                        user_agent=request.META.get('HTTP_USER_AGENT', '')
                    )
                    
                    # Create device footprint
                    DeviceFootprint.objects.create(
                        checkpoint_attendance=attendance,
                        screen_resolution=device_info.get('screen', ''),
                        timezone=device_info.get('timezone', ''),
                        language=device_info.get('language', ''),
                        platform=device_info.get('platform', ''),
                        browser_fingerprint=json.dumps(device_info)
                    )
                    
                    # Determine status
                    status_message = "on time"
                    if attendance.is_late:
                        status_message = "late"
                    elif not attendance.is_on_time and not attendance.is_late:
                        status_message = "early"
                    
                    return JsonResponse({
                        'success': True,
                        'message': f'Checkpoint attendance recorded successfully ({status_message})',
                        'attendee_name': attendee.full_name,
                        'event_name': event.name,
                        'checkpoint_name': checkpoint.name,
                        'status': status_message,
                        'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    })
                    
                except AttendanceCheckpoint.DoesNotExist:
                    return JsonResponse({
                        'success': False,
                        'error': 'Invalid checkpoint.'
                    })
            else:
                # Record general event attendance
                if event.event_type == 'single':
                    # Check for existing attendance
                    if AttendanceRecord.objects.filter(event=event, attendee=attendee).exists():
                        return JsonResponse({
                            'success': False,
                            'error': 'Attendance already recorded for this event.'
                        })
                    
                    # Create attendance record
                    attendance = AttendanceRecord.objects.create(
                        event=event,
                        attendee=attendee,
                        device_fingerprint=json.dumps(device_info),
                        ip_address=ip,
                        user_agent=request.META.get('HTTP_USER_AGENT', '')
                    )
                    
                    # Create device footprint
                    DeviceFootprint.objects.create(
                        attendance_record=attendance,
                        screen_resolution=device_info.get('screen', ''),
                        timezone=device_info.get('timezone', ''),
                        language=device_info.get('language', ''),
                        platform=device_info.get('platform', ''),
                        browser_fingerprint=json.dumps(device_info)
                    )
                    
                    return JsonResponse({
                        'success': True,
                        'message': f'Attendance recorded successfully for {attendee.full_name}',
                        'attendee_name': attendee.full_name,
                        'event_name': event.name,
                        'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    })
                else:
                    # For multi-day events, find the session for target date
                    try:
                        session = event.eventsession_set.get(session_date=target_date)
                        
                        # Check for existing session attendance
                        if SessionAttendance.objects.filter(event_session=session, attendee=attendee).exists():
                            return JsonResponse({
                                'success': False,
                                'error': 'Attendance already recorded for this session.'
                            })
                        
                        # Create session attendance
                        attendance = SessionAttendance.objects.create(
                            event_session=session,
                            attendee=attendee,
                            device_fingerprint=json.dumps(device_info),
                            ip_address=ip,
                            user_agent=request.META.get('HTTP_USER_AGENT', '')
                        )
                        
                        # Create device footprint
                        DeviceFootprint.objects.create(
                            session_attendance=attendance,
                            screen_resolution=device_info.get('screen', ''),
                            timezone=device_info.get('timezone', ''),
                            language=device_info.get('language', ''),
                            platform=device_info.get('platform', ''),
                            browser_fingerprint=json.dumps(device_info)
                        )
                        
                        return JsonResponse({
                            'success': True,
                            'message': f'Session attendance recorded successfully for {attendee.full_name}',
                            'attendee_name': attendee.full_name,
                            'event_name': event.name,
                            'session_info': f'Session {session.session_number} - {session.session_date}',
                            'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                        })
                        
                    except:
                        return JsonResponse({
                            'success': False,
                            'error': f'No session found for {target_date}.'
                        })
            
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON data.'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'An error occurred: {str(e)}'
            })


@method_decorator(csrf_exempt, name='dispatch')
class GetSessionCheckpointsView(View):
    def get(self, request, session_id):
        try:
            session = EventSession.objects.get(pk=session_id)
            checkpoints = AttendanceCheckpoint.objects.filter(
                event_session=session, is_active=True
            ).order_by('order')
            
            checkpoint_data = []
            for checkpoint in checkpoints:
                checkpoint_data.append({
                    'id': checkpoint.id,
                    'name': checkpoint.name,
                    'checkpoint_type': checkpoint.checkpoint_type,
                    'required_time': checkpoint.required_time.strftime('%H:%M'),
                    'window_start': checkpoint.window_start.strftime('%H:%M'),
                    'window_end': checkpoint.window_end.strftime('%H:%M'),
                    'order': checkpoint.order,
                    'checkpoint_code': checkpoint.checkpoint_code
                })
            
            return JsonResponse({
                'success': True,
                'checkpoints': checkpoint_data
            })
            
        except EventSession.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Session not found.'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'An error occurred: {str(e)}'
            })


@method_decorator(csrf_exempt, name='dispatch')
class RecordUnifiedAttendanceView(View):
    """Record attendance for events with dynamic checkpoint selection"""
    def post(self, request):
        try:
            data = json.loads(request.body)
            qr_code = data.get('qr_code')
            attendee_id = data.get('attendee_id')
            checkpoint_id = data.get('checkpoint_id')  # Can be None for simple attendance
            target_date = data.get('target_date')  # Optional, defaults to today
            device_info = data.get('device_info', {})
            
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
            
            if checkpoint_id:
                # Record checkpoint attendance
                try:
                    checkpoint = AttendanceCheckpoint.objects.get(
                        id=checkpoint_id, is_active=True
                    )
                    
                    # Verify checkpoint belongs to this event
                    if checkpoint.event != event and (not checkpoint.event_session or checkpoint.event_session.event != event):
                        return JsonResponse({
                            'success': False,
                            'error': 'Checkpoint does not belong to this event.'
                        })
                    
                    # Check if checkpoint applies to this date
                    if not checkpoint.applies_to_date(target_date):
                        return JsonResponse({
                            'success': False,
                            'error': f'This checkpoint does not apply to {target_date}.'
                        })
                    
                    # Check for existing checkpoint attendance
                    existing_checkpoint = CheckpointAttendance.objects.filter(
                        checkpoint=checkpoint,
                        attendee=attendee,
                        timestamp__date=target_date
                    ).first()
                    
                    if existing_checkpoint:
                        return JsonResponse({
                            'success': False,
                            'error': 'Attendance already recorded for this checkpoint today.'
                        })
                    
                    # Create checkpoint attendance
                    attendance = CheckpointAttendance.objects.create(
                        checkpoint=checkpoint,
                        attendee=attendee,
                        event=checkpoint.event,
                        event_session=checkpoint.event_session,
                        device_fingerprint=json.dumps(device_info),
                        ip_address=ip,
                        user_agent=request.META.get('HTTP_USER_AGENT', '')
                    )
                    
                    # Create device footprint
                    DeviceFootprint.objects.create(
                        checkpoint_attendance=attendance,
                        screen_resolution=device_info.get('screen', ''),
                        timezone=device_info.get('timezone', ''),
                        language=device_info.get('language', ''),
                        platform=device_info.get('platform', ''),
                        browser_fingerprint=json.dumps(device_info)
                    )
                    
                    # Determine status
                    status_message = "on time"
                    if attendance.is_late:
                        status_message = "late"
                    elif not attendance.is_on_time and not attendance.is_late:
                        status_message = "early"
                    
                    return JsonResponse({
                        'success': True,
                        'message': f'Checkpoint attendance recorded successfully ({status_message})',
                        'attendee_name': attendee.full_name,
                        'event_name': event.name,
                        'checkpoint_name': checkpoint.name,
                        'status': status_message,
                        'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    })
                    
                except AttendanceCheckpoint.DoesNotExist:
                    return JsonResponse({
                        'success': False,
                        'error': 'Invalid checkpoint.'
                    })
            else:
                # Record general event attendance
                if event.event_type == 'single':
                    # Check for existing attendance
                    if AttendanceRecord.objects.filter(event=event, attendee=attendee).exists():
                        return JsonResponse({
                            'success': False,
                            'error': 'Attendance already recorded for this event.'
                        })
                    
                    # Create attendance record
                    attendance = AttendanceRecord.objects.create(
                        event=event,
                        attendee=attendee,
                        device_fingerprint=json.dumps(device_info),
                        ip_address=ip,
                        user_agent=request.META.get('HTTP_USER_AGENT', '')
                    )
                    
                    # Create device footprint
                    DeviceFootprint.objects.create(
                        attendance_record=attendance,
                        screen_resolution=device_info.get('screen', ''),
                        timezone=device_info.get('timezone', ''),
                        language=device_info.get('language', ''),
                        platform=device_info.get('platform', ''),
                        browser_fingerprint=json.dumps(device_info)
                    )
                    
                    return JsonResponse({
                        'success': True,
                        'message': f'Attendance recorded successfully for {attendee.full_name}',
                        'attendee_name': attendee.full_name,
                        'event_name': event.name,
                        'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    })
                else:
                    # For multi-day events, find the session for target date
                    try:
                        session = event.eventsession_set.get(session_date=target_date)
                        
                        # Check for existing session attendance
                        if SessionAttendance.objects.filter(event_session=session, attendee=attendee).exists():
                            return JsonResponse({
                                'success': False,
                                'error': 'Attendance already recorded for this session.'
                            })
                        
                        # Create session attendance
                        attendance = SessionAttendance.objects.create(
                            event_session=session,
                            attendee=attendee,
                            device_fingerprint=json.dumps(device_info),
                            ip_address=ip,
                            user_agent=request.META.get('HTTP_USER_AGENT', '')
                        )
                        
                        # Create device footprint
                        DeviceFootprint.objects.create(
                            session_attendance=attendance,
                            screen_resolution=device_info.get('screen', ''),
                            timezone=device_info.get('timezone', ''),
                            language=device_info.get('language', ''),
                            platform=device_info.get('platform', ''),
                            browser_fingerprint=json.dumps(device_info)
                        )
                        
                        return JsonResponse({
                            'success': True,
                            'message': f'Session attendance recorded successfully for {attendee.full_name}',
                            'attendee_name': attendee.full_name,
                            'event_name': event.name,
                            'session_info': f'Session {session.session_number} - {session.session_date}',
                            'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                        })
                        
                    except:
                        return JsonResponse({
                            'success': False,
                            'error': f'No session found for {target_date}.'
                        })
            
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON data.'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'An error occurred: {str(e)}'
            })


@method_decorator(csrf_exempt, name='dispatch')
class ValidateAttendeeIDView(View):
    def post(self, request):
        try:
            data = json.loads(request.body)
            attendee_id = data.get('attendee_id')
            
            try:
                attendee = Attendee.objects.get(attendee_id=attendee_id, is_active=True)
                return JsonResponse({
                    'success': True,
                    'attendee_name': attendee.full_name
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
                'error': f'An error occurred: {str(e)}'
            })


@method_decorator(csrf_exempt, name='dispatch')
class RecordUnifiedAttendanceView(View):
    """Record attendance for events with dynamic checkpoint selection"""
    def post(self, request):
        try:
            data = json.loads(request.body)
            qr_code = data.get('qr_code')
            attendee_id = data.get('attendee_id')
            checkpoint_id = data.get('checkpoint_id')  # Can be None for simple attendance
            target_date = data.get('target_date')  # Optional, defaults to today
            device_info = data.get('device_info', {})
            
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
            
            if checkpoint_id:
                # Record checkpoint attendance
                try:
                    checkpoint = AttendanceCheckpoint.objects.get(
                        id=checkpoint_id, is_active=True
                    )
                    
                    # Verify checkpoint belongs to this event
                    if checkpoint.event != event and (not checkpoint.event_session or checkpoint.event_session.event != event):
                        return JsonResponse({
                            'success': False,
                            'error': 'Checkpoint does not belong to this event.'
                        })
                    
                    # Check if checkpoint applies to this date
                    if not checkpoint.applies_to_date(target_date):
                        return JsonResponse({
                            'success': False,
                            'error': f'This checkpoint does not apply to {target_date}.'
                        })
                    
                    # Check for existing checkpoint attendance
                    existing_checkpoint = CheckpointAttendance.objects.filter(
                        checkpoint=checkpoint,
                        attendee=attendee,
                        timestamp__date=target_date
                    ).first()
                    
                    if existing_checkpoint:
                        return JsonResponse({
                            'success': False,
                            'error': 'Attendance already recorded for this checkpoint today.'
                        })
                    
                    # Create checkpoint attendance
                    attendance = CheckpointAttendance.objects.create(
                        checkpoint=checkpoint,
                        attendee=attendee,
                        event=checkpoint.event,
                        event_session=checkpoint.event_session,
                        device_fingerprint=json.dumps(device_info),
                        ip_address=ip,
                        user_agent=request.META.get('HTTP_USER_AGENT', '')
                    )
                    
                    # Create device footprint
                    DeviceFootprint.objects.create(
                        checkpoint_attendance=attendance,
                        screen_resolution=device_info.get('screen', ''),
                        timezone=device_info.get('timezone', ''),
                        language=device_info.get('language', ''),
                        platform=device_info.get('platform', ''),
                        browser_fingerprint=json.dumps(device_info)
                    )
                    
                    # Determine status
                    status_message = "on time"
                    if attendance.is_late:
                        status_message = "late"
                    elif not attendance.is_on_time and not attendance.is_late:
                        status_message = "early"
                    
                    return JsonResponse({
                        'success': True,
                        'message': f'Checkpoint attendance recorded successfully ({status_message})',
                        'attendee_name': attendee.full_name,
                        'event_name': event.name,
                        'checkpoint_name': checkpoint.name,
                        'status': status_message,
                        'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    })
                    
                except AttendanceCheckpoint.DoesNotExist:
                    return JsonResponse({
                        'success': False,
                        'error': 'Invalid checkpoint.'
                    })
            else:
                # Record general event attendance
                if event.event_type == 'single':
                    # Check for existing attendance
                    if AttendanceRecord.objects.filter(event=event, attendee=attendee).exists():
                        return JsonResponse({
                            'success': False,
                            'error': 'Attendance already recorded for this event.'
                        })
                    
                    # Create attendance record
                    attendance = AttendanceRecord.objects.create(
                        event=event,
                        attendee=attendee,
                        device_fingerprint=json.dumps(device_info),
                        ip_address=ip,
                        user_agent=request.META.get('HTTP_USER_AGENT', '')
                    )
                    
                    # Create device footprint
                    DeviceFootprint.objects.create(
                        attendance_record=attendance,
                        screen_resolution=device_info.get('screen', ''),
                        timezone=device_info.get('timezone', ''),
                        language=device_info.get('language', ''),
                        platform=device_info.get('platform', ''),
                        browser_fingerprint=json.dumps(device_info)
                    )
                    
                    return JsonResponse({
                        'success': True,
                        'message': f'Attendance recorded successfully for {attendee.full_name}',
                        'attendee_name': attendee.full_name,
                        'event_name': event.name,
                        'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    })
                else:
                    # For multi-day events, find the session for target date
                    try:
                        session = event.eventsession_set.get(session_date=target_date)
                        
                        # Check for existing session attendance
                        if SessionAttendance.objects.filter(event_session=session, attendee=attendee).exists():
                            return JsonResponse({
                                'success': False,
                                'error': 'Attendance already recorded for this session.'
                            })
                        
                        # Create session attendance
                        attendance = SessionAttendance.objects.create(
                            event_session=session,
                            attendee=attendee,
                            device_fingerprint=json.dumps(device_info),
                            ip_address=ip,
                            user_agent=request.META.get('HTTP_USER_AGENT', '')
                        )
                        
                        # Create device footprint
                        DeviceFootprint.objects.create(
                            session_attendance=attendance,
                            screen_resolution=device_info.get('screen', ''),
                            timezone=device_info.get('timezone', ''),
                            language=device_info.get('language', ''),
                            platform=device_info.get('platform', ''),
                            browser_fingerprint=json.dumps(device_info)
                        )
                        
                        return JsonResponse({
                            'success': True,
                            'message': f'Session attendance recorded successfully for {attendee.full_name}',
                            'attendee_name': attendee.full_name,
                            'event_name': event.name,
                            'session_info': f'Session {session.session_number} - {session.session_date}',
                            'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                        })
                        
                    except:
                        return JsonResponse({
                            'success': False,
                            'error': f'No session found for {target_date}.'
                        })
            
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON data.'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'An error occurred: {str(e)}'
            })


class CheckpointScanView(TemplateView):
    template_name = 'attendance/checkpoint_scan.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        checkpoint_code = kwargs.get('checkpoint_code')
        
        try:
            checkpoint = AttendanceCheckpoint.objects.select_related('event', 'event_session').get(
                checkpoint_code=checkpoint_code, is_active=True
            )
            context['checkpoint'] = checkpoint
            context['event'] = checkpoint.event or checkpoint.event_session.event
            context['event_session'] = checkpoint.event_session
            context['valid_qr'] = True
            
            # Get current time to show if checkpoint is active
            from django.utils import timezone
            current_time = timezone.now().time()
            context['is_within_window'] = checkpoint.is_within_window(current_time)
            context['window_start'] = checkpoint.window_start
            context['window_end'] = checkpoint.window_end
            
        except AttendanceCheckpoint.DoesNotExist:
            context['valid_qr'] = False
            context['error'] = 'Invalid checkpoint QR code.'
        
        return context


@method_decorator(csrf_exempt, name='dispatch')
class RecordCheckpointAttendanceView(View):
    def post(self, request):
        try:
            data = json.loads(request.body)
            checkpoint_code = data.get('checkpoint_code')
            attendee_id = data.get('attendee_id')
            device_info = data.get('device_info', {})
            
            # Validate checkpoint
            try:
                checkpoint = AttendanceCheckpoint.objects.select_related('event', 'event_session').get(
                    checkpoint_code=checkpoint_code, is_active=True
                )
            except AttendanceCheckpoint.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid checkpoint QR code.'
                })
            
            # Validate attendee
            try:
                attendee = Attendee.objects.get(attendee_id=attendee_id, is_active=True)
            except Attendee.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid attendee ID.'
                })
            
            # Check if already attended this checkpoint
            existing_attendance = None
            if checkpoint.event:
                existing_attendance = CheckpointAttendance.objects.filter(
                    checkpoint=checkpoint, attendee=attendee, event=checkpoint.event
                ).first()
            elif checkpoint.event_session:
                existing_attendance = CheckpointAttendance.objects.filter(
                    checkpoint=checkpoint, attendee=attendee, event_session=checkpoint.event_session
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
            
            # Create checkpoint attendance record
            attendance = CheckpointAttendance.objects.create(
                checkpoint=checkpoint,
                attendee=attendee,
                event=checkpoint.event,
                event_session=checkpoint.event_session,
                device_fingerprint=json.dumps(device_info),
                ip_address=ip,
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            
            # Create device footprint
            DeviceFootprint.objects.create(
                checkpoint_attendance=attendance,
                screen_resolution=device_info.get('screen', ''),
                timezone=device_info.get('timezone', ''),
                language=device_info.get('language', ''),
                platform=device_info.get('platform', ''),
                browser_fingerprint=json.dumps(device_info)
            )
            
            # Determine status message
            status_message = "on time"
            if attendance.is_late:
                status_message = "late"
            elif not attendance.is_on_time and not attendance.is_late:
                status_message = "early"
            
            event_name = checkpoint.event.name if checkpoint.event else checkpoint.event_session.event.name
            
            return JsonResponse({
                'success': True,
                'message': f'Checkpoint attendance recorded successfully ({status_message})',
                'attendee_name': attendee.full_name,
                'event_name': event_name,
                'checkpoint_name': checkpoint.name,
                'checkpoint_time': checkpoint.required_time.strftime('%H:%M'),
                'status': status_message,
                'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
            })
            
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON data.'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'An error occurred: {str(e)}'
            })


@method_decorator(csrf_exempt, name='dispatch')
class RecordUnifiedAttendanceView(View):
    """Record attendance for events with dynamic checkpoint selection"""
    def post(self, request):
        try:
            data = json.loads(request.body)
            qr_code = data.get('qr_code')
            attendee_id = data.get('attendee_id')
            checkpoint_id = data.get('checkpoint_id')  # Can be None for simple attendance
            target_date = data.get('target_date')  # Optional, defaults to today
            device_info = data.get('device_info', {})
            
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
            
            if checkpoint_id:
                # Record checkpoint attendance
                try:
                    checkpoint = AttendanceCheckpoint.objects.get(
                        id=checkpoint_id, is_active=True
                    )
                    
                    # Verify checkpoint belongs to this event
                    if checkpoint.event != event and (not checkpoint.event_session or checkpoint.event_session.event != event):
                        return JsonResponse({
                            'success': False,
                            'error': 'Checkpoint does not belong to this event.'
                        })
                    
                    # Check if checkpoint applies to this date
                    if not checkpoint.applies_to_date(target_date):
                        return JsonResponse({
                            'success': False,
                            'error': f'This checkpoint does not apply to {target_date}.'
                        })
                    
                    # Check for existing checkpoint attendance
                    existing_checkpoint = CheckpointAttendance.objects.filter(
                        checkpoint=checkpoint,
                        attendee=attendee,
                        timestamp__date=target_date
                    ).first()
                    
                    if existing_checkpoint:
                        return JsonResponse({
                            'success': False,
                            'error': 'Attendance already recorded for this checkpoint today.'
                        })
                    
                    # Create checkpoint attendance
                    attendance = CheckpointAttendance.objects.create(
                        checkpoint=checkpoint,
                        attendee=attendee,
                        event=checkpoint.event,
                        event_session=checkpoint.event_session,
                        device_fingerprint=json.dumps(device_info),
                        ip_address=ip,
                        user_agent=request.META.get('HTTP_USER_AGENT', '')
                    )
                    
                    # Create device footprint
                    DeviceFootprint.objects.create(
                        checkpoint_attendance=attendance,
                        screen_resolution=device_info.get('screen', ''),
                        timezone=device_info.get('timezone', ''),
                        language=device_info.get('language', ''),
                        platform=device_info.get('platform', ''),
                        browser_fingerprint=json.dumps(device_info)
                    )
                    
                    # Determine status
                    status_message = "on time"
                    if attendance.is_late:
                        status_message = "late"
                    elif not attendance.is_on_time and not attendance.is_late:
                        status_message = "early"
                    
                    return JsonResponse({
                        'success': True,
                        'message': f'Checkpoint attendance recorded successfully ({status_message})',
                        'attendee_name': attendee.full_name,
                        'event_name': event.name,
                        'checkpoint_name': checkpoint.name,
                        'status': status_message,
                        'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    })
                    
                except AttendanceCheckpoint.DoesNotExist:
                    return JsonResponse({
                        'success': False,
                        'error': 'Invalid checkpoint.'
                    })
            else:
                # Record general event attendance
                if event.event_type == 'single':
                    # Check for existing attendance
                    if AttendanceRecord.objects.filter(event=event, attendee=attendee).exists():
                        return JsonResponse({
                            'success': False,
                            'error': 'Attendance already recorded for this event.'
                        })
                    
                    # Create attendance record
                    attendance = AttendanceRecord.objects.create(
                        event=event,
                        attendee=attendee,
                        device_fingerprint=json.dumps(device_info),
                        ip_address=ip,
                        user_agent=request.META.get('HTTP_USER_AGENT', '')
                    )
                    
                    # Create device footprint
                    DeviceFootprint.objects.create(
                        attendance_record=attendance,
                        screen_resolution=device_info.get('screen', ''),
                        timezone=device_info.get('timezone', ''),
                        language=device_info.get('language', ''),
                        platform=device_info.get('platform', ''),
                        browser_fingerprint=json.dumps(device_info)
                    )
                    
                    return JsonResponse({
                        'success': True,
                        'message': f'Attendance recorded successfully for {attendee.full_name}',
                        'attendee_name': attendee.full_name,
                        'event_name': event.name,
                        'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    })
                else:
                    # For multi-day events, find the session for target date
                    try:
                        session = event.eventsession_set.get(session_date=target_date)
                        
                        # Check for existing session attendance
                        if SessionAttendance.objects.filter(event_session=session, attendee=attendee).exists():
                            return JsonResponse({
                                'success': False,
                                'error': 'Attendance already recorded for this session.'
                            })
                        
                        # Create session attendance
                        attendance = SessionAttendance.objects.create(
                            event_session=session,
                            attendee=attendee,
                            device_fingerprint=json.dumps(device_info),
                            ip_address=ip,
                            user_agent=request.META.get('HTTP_USER_AGENT', '')
                        )
                        
                        # Create device footprint
                        DeviceFootprint.objects.create(
                            session_attendance=attendance,
                            screen_resolution=device_info.get('screen', ''),
                            timezone=device_info.get('timezone', ''),
                            language=device_info.get('language', ''),
                            platform=device_info.get('platform', ''),
                            browser_fingerprint=json.dumps(device_info)
                        )
                        
                        return JsonResponse({
                            'success': True,
                            'message': f'Session attendance recorded successfully for {attendee.full_name}',
                            'attendee_name': attendee.full_name,
                            'event_name': event.name,
                            'session_info': f'Session {session.session_number} - {session.session_date}',
                            'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                        })
                        
                    except:
                        return JsonResponse({
                            'success': False,
                            'error': f'No session found for {target_date}.'
                        })
            
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON data.'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'An error occurred: {str(e)}'
            })


@method_decorator(csrf_exempt, name='dispatch')
class GetEventCheckpointsView(View):
    def get(self, request, event_id):
        try:
            event = Event.objects.get(pk=event_id)
            checkpoints = AttendanceCheckpoint.objects.filter(
                event=event, is_active=True
            ).order_by('order')
            
            checkpoint_data = []
            for checkpoint in checkpoints:
                checkpoint_data.append({
                    'id': checkpoint.id,
                    'name': checkpoint.name,
                    'checkpoint_type': checkpoint.checkpoint_type,
                    'required_time': checkpoint.required_time.strftime('%H:%M'),
                    'window_start': checkpoint.window_start.strftime('%H:%M'),
                    'window_end': checkpoint.window_end.strftime('%H:%M'),
                    'order': checkpoint.order,
                    'checkpoint_code': checkpoint.checkpoint_code
                })
            
            return JsonResponse({
                'success': True,
                'checkpoints': checkpoint_data
            })
            
        except Event.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Event not found.'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'An error occurred: {str(e)}'
            })


@method_decorator(csrf_exempt, name='dispatch')
class RecordUnifiedAttendanceView(View):
    """Record attendance for events with dynamic checkpoint selection"""
    def post(self, request):
        try:
            data = json.loads(request.body)
            qr_code = data.get('qr_code')
            attendee_id = data.get('attendee_id')
            checkpoint_id = data.get('checkpoint_id')  # Can be None for simple attendance
            target_date = data.get('target_date')  # Optional, defaults to today
            device_info = data.get('device_info', {})
            
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
            
            if checkpoint_id:
                # Record checkpoint attendance
                try:
                    checkpoint = AttendanceCheckpoint.objects.get(
                        id=checkpoint_id, is_active=True
                    )
                    
                    # Verify checkpoint belongs to this event
                    if checkpoint.event != event and (not checkpoint.event_session or checkpoint.event_session.event != event):
                        return JsonResponse({
                            'success': False,
                            'error': 'Checkpoint does not belong to this event.'
                        })
                    
                    # Check if checkpoint applies to this date
                    if not checkpoint.applies_to_date(target_date):
                        return JsonResponse({
                            'success': False,
                            'error': f'This checkpoint does not apply to {target_date}.'
                        })
                    
                    # Check for existing checkpoint attendance
                    existing_checkpoint = CheckpointAttendance.objects.filter(
                        checkpoint=checkpoint,
                        attendee=attendee,
                        timestamp__date=target_date
                    ).first()
                    
                    if existing_checkpoint:
                        return JsonResponse({
                            'success': False,
                            'error': 'Attendance already recorded for this checkpoint today.'
                        })
                    
                    # Create checkpoint attendance
                    attendance = CheckpointAttendance.objects.create(
                        checkpoint=checkpoint,
                        attendee=attendee,
                        event=checkpoint.event,
                        event_session=checkpoint.event_session,
                        device_fingerprint=json.dumps(device_info),
                        ip_address=ip,
                        user_agent=request.META.get('HTTP_USER_AGENT', '')
                    )
                    
                    # Create device footprint
                    DeviceFootprint.objects.create(
                        checkpoint_attendance=attendance,
                        screen_resolution=device_info.get('screen', ''),
                        timezone=device_info.get('timezone', ''),
                        language=device_info.get('language', ''),
                        platform=device_info.get('platform', ''),
                        browser_fingerprint=json.dumps(device_info)
                    )
                    
                    # Determine status
                    status_message = "on time"
                    if attendance.is_late:
                        status_message = "late"
                    elif not attendance.is_on_time and not attendance.is_late:
                        status_message = "early"
                    
                    return JsonResponse({
                        'success': True,
                        'message': f'Checkpoint attendance recorded successfully ({status_message})',
                        'attendee_name': attendee.full_name,
                        'event_name': event.name,
                        'checkpoint_name': checkpoint.name,
                        'status': status_message,
                        'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    })
                    
                except AttendanceCheckpoint.DoesNotExist:
                    return JsonResponse({
                        'success': False,
                        'error': 'Invalid checkpoint.'
                    })
            else:
                # Record general event attendance
                if event.event_type == 'single':
                    # Check for existing attendance
                    if AttendanceRecord.objects.filter(event=event, attendee=attendee).exists():
                        return JsonResponse({
                            'success': False,
                            'error': 'Attendance already recorded for this event.'
                        })
                    
                    # Create attendance record
                    attendance = AttendanceRecord.objects.create(
                        event=event,
                        attendee=attendee,
                        device_fingerprint=json.dumps(device_info),
                        ip_address=ip,
                        user_agent=request.META.get('HTTP_USER_AGENT', '')
                    )
                    
                    # Create device footprint
                    DeviceFootprint.objects.create(
                        attendance_record=attendance,
                        screen_resolution=device_info.get('screen', ''),
                        timezone=device_info.get('timezone', ''),
                        language=device_info.get('language', ''),
                        platform=device_info.get('platform', ''),
                        browser_fingerprint=json.dumps(device_info)
                    )
                    
                    return JsonResponse({
                        'success': True,
                        'message': f'Attendance recorded successfully for {attendee.full_name}',
                        'attendee_name': attendee.full_name,
                        'event_name': event.name,
                        'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    })
                else:
                    # For multi-day events, find the session for target date
                    try:
                        session = event.eventsession_set.get(session_date=target_date)
                        
                        # Check for existing session attendance
                        if SessionAttendance.objects.filter(event_session=session, attendee=attendee).exists():
                            return JsonResponse({
                                'success': False,
                                'error': 'Attendance already recorded for this session.'
                            })
                        
                        # Create session attendance
                        attendance = SessionAttendance.objects.create(
                            event_session=session,
                            attendee=attendee,
                            device_fingerprint=json.dumps(device_info),
                            ip_address=ip,
                            user_agent=request.META.get('HTTP_USER_AGENT', '')
                        )
                        
                        # Create device footprint
                        DeviceFootprint.objects.create(
                            session_attendance=attendance,
                            screen_resolution=device_info.get('screen', ''),
                            timezone=device_info.get('timezone', ''),
                            language=device_info.get('language', ''),
                            platform=device_info.get('platform', ''),
                            browser_fingerprint=json.dumps(device_info)
                        )
                        
                        return JsonResponse({
                            'success': True,
                            'message': f'Session attendance recorded successfully for {attendee.full_name}',
                            'attendee_name': attendee.full_name,
                            'event_name': event.name,
                            'session_info': f'Session {session.session_number} - {session.session_date}',
                            'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                        })
                        
                    except:
                        return JsonResponse({
                            'success': False,
                            'error': f'No session found for {target_date}.'
                        })
            
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON data.'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'An error occurred: {str(e)}'
            })


@method_decorator(csrf_exempt, name='dispatch')
class GetSessionCheckpointsView(View):
    def get(self, request, session_id):
        try:
            session = EventSession.objects.get(pk=session_id)
            checkpoints = AttendanceCheckpoint.objects.filter(
                event_session=session, is_active=True
            ).order_by('order')
            
            checkpoint_data = []
            for checkpoint in checkpoints:
                checkpoint_data.append({
                    'id': checkpoint.id,
                    'name': checkpoint.name,
                    'checkpoint_type': checkpoint.checkpoint_type,
                    'required_time': checkpoint.required_time.strftime('%H:%M'),
                    'window_start': checkpoint.window_start.strftime('%H:%M'),
                    'window_end': checkpoint.window_end.strftime('%H:%M'),
                    'order': checkpoint.order,
                    'checkpoint_code': checkpoint.checkpoint_code
                })
            
            return JsonResponse({
                'success': True,
                'checkpoints': checkpoint_data
            })
            
        except EventSession.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Session not found.'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'An error occurred: {str(e)}'
            })


@method_decorator(csrf_exempt, name='dispatch')
class RecordUnifiedAttendanceView(View):
    """Record attendance for events with dynamic checkpoint selection"""
    def post(self, request):
        try:
            data = json.loads(request.body)
            qr_code = data.get('qr_code')
            attendee_id = data.get('attendee_id')
            checkpoint_id = data.get('checkpoint_id')  # Can be None for simple attendance
            target_date = data.get('target_date')  # Optional, defaults to today
            device_info = data.get('device_info', {})
            
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
            
            if checkpoint_id:
                # Record checkpoint attendance
                try:
                    checkpoint = AttendanceCheckpoint.objects.get(
                        id=checkpoint_id, is_active=True
                    )
                    
                    # Verify checkpoint belongs to this event
                    if checkpoint.event != event and (not checkpoint.event_session or checkpoint.event_session.event != event):
                        return JsonResponse({
                            'success': False,
                            'error': 'Checkpoint does not belong to this event.'
                        })
                    
                    # Check if checkpoint applies to this date
                    if not checkpoint.applies_to_date(target_date):
                        return JsonResponse({
                            'success': False,
                            'error': f'This checkpoint does not apply to {target_date}.'
                        })
                    
                    # Check for existing checkpoint attendance
                    existing_checkpoint = CheckpointAttendance.objects.filter(
                        checkpoint=checkpoint,
                        attendee=attendee,
                        timestamp__date=target_date
                    ).first()
                    
                    if existing_checkpoint:
                        return JsonResponse({
                            'success': False,
                            'error': 'Attendance already recorded for this checkpoint today.'
                        })
                    
                    # Create checkpoint attendance
                    attendance = CheckpointAttendance.objects.create(
                        checkpoint=checkpoint,
                        attendee=attendee,
                        event=checkpoint.event,
                        event_session=checkpoint.event_session,
                        device_fingerprint=json.dumps(device_info),
                        ip_address=ip,
                        user_agent=request.META.get('HTTP_USER_AGENT', '')
                    )
                    
                    # Create device footprint
                    DeviceFootprint.objects.create(
                        checkpoint_attendance=attendance,
                        screen_resolution=device_info.get('screen', ''),
                        timezone=device_info.get('timezone', ''),
                        language=device_info.get('language', ''),
                        platform=device_info.get('platform', ''),
                        browser_fingerprint=json.dumps(device_info)
                    )
                    
                    # Determine status
                    status_message = "on time"
                    if attendance.is_late:
                        status_message = "late"
                    elif not attendance.is_on_time and not attendance.is_late:
                        status_message = "early"
                    
                    return JsonResponse({
                        'success': True,
                        'message': f'Checkpoint attendance recorded successfully ({status_message})',
                        'attendee_name': attendee.full_name,
                        'event_name': event.name,
                        'checkpoint_name': checkpoint.name,
                        'status': status_message,
                        'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    })
                    
                except AttendanceCheckpoint.DoesNotExist:
                    return JsonResponse({
                        'success': False,
                        'error': 'Invalid checkpoint.'
                    })
            else:
                # Record general event attendance
                if event.event_type == 'single':
                    # Check for existing attendance
                    if AttendanceRecord.objects.filter(event=event, attendee=attendee).exists():
                        return JsonResponse({
                            'success': False,
                            'error': 'Attendance already recorded for this event.'
                        })
                    
                    # Create attendance record
                    attendance = AttendanceRecord.objects.create(
                        event=event,
                        attendee=attendee,
                        device_fingerprint=json.dumps(device_info),
                        ip_address=ip,
                        user_agent=request.META.get('HTTP_USER_AGENT', '')
                    )
                    
                    # Create device footprint
                    DeviceFootprint.objects.create(
                        attendance_record=attendance,
                        screen_resolution=device_info.get('screen', ''),
                        timezone=device_info.get('timezone', ''),
                        language=device_info.get('language', ''),
                        platform=device_info.get('platform', ''),
                        browser_fingerprint=json.dumps(device_info)
                    )
                    
                    return JsonResponse({
                        'success': True,
                        'message': f'Attendance recorded successfully for {attendee.full_name}',
                        'attendee_name': attendee.full_name,
                        'event_name': event.name,
                        'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    })
                else:
                    # For multi-day events, find the session for target date
                    try:
                        session = event.eventsession_set.get(session_date=target_date)
                        
                        # Check for existing session attendance
                        if SessionAttendance.objects.filter(event_session=session, attendee=attendee).exists():
                            return JsonResponse({
                                'success': False,
                                'error': 'Attendance already recorded for this session.'
                            })
                        
                        # Create session attendance
                        attendance = SessionAttendance.objects.create(
                            event_session=session,
                            attendee=attendee,
                            device_fingerprint=json.dumps(device_info),
                            ip_address=ip,
                            user_agent=request.META.get('HTTP_USER_AGENT', '')
                        )
                        
                        # Create device footprint
                        DeviceFootprint.objects.create(
                            session_attendance=attendance,
                            screen_resolution=device_info.get('screen', ''),
                            timezone=device_info.get('timezone', ''),
                            language=device_info.get('language', ''),
                            platform=device_info.get('platform', ''),
                            browser_fingerprint=json.dumps(device_info)
                        )
                        
                        return JsonResponse({
                            'success': True,
                            'message': f'Session attendance recorded successfully for {attendee.full_name}',
                            'attendee_name': attendee.full_name,
                            'event_name': event.name,
                            'session_info': f'Session {session.session_number} - {session.session_date}',
                            'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                        })
                        
                    except:
                        return JsonResponse({
                            'success': False,
                            'error': f'No session found for {target_date}.'
                        })
            
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON data.'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'An error occurred: {str(e)}'
            })


class SessionScanView(TemplateView):
    template_name = 'attendance/session_scan.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qr_code = kwargs.get('qr_code')
        
        try:
            session = EventSession.objects.get(qr_code=qr_code, is_active=True)
            context['session'] = session
            context['event'] = session.event
            context['valid_qr'] = True
        except EventSession.DoesNotExist:
            context['valid_qr'] = False
            context['error'] = 'Invalid QR code or session not found.'
        
        return context


@method_decorator(csrf_exempt, name='dispatch')
class RecordSessionAttendanceView(View):
    def post(self, request):
        try:
            data = json.loads(request.body)
            qr_code = data.get('qr_code')
            attendee_id = data.get('attendee_id')
            device_info = data.get('device_info', {})
            
            # Validate session
            try:
                session = EventSession.objects.get(qr_code=qr_code, is_active=True)
            except EventSession.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid QR code or session not found.'
                })
            
            # Validate attendee
            try:
                attendee = Attendee.objects.get(attendee_id=attendee_id, is_active=True)
            except Attendee.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid attendee ID.'
                })
            
            # Check if already attended this session
            if SessionAttendance.objects.filter(event_session=session, attendee=attendee).exists():
                return JsonResponse({
                    'success': False,
                    'error': 'Attendance already recorded for this session.'
                })
            
            # Get client IP
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip = x_forwarded_for.split(',')[0]
            else:
                ip = request.META.get('REMOTE_ADDR')
            
            # Create session attendance record
            attendance = SessionAttendance.objects.create(
                event_session=session,
                attendee=attendee,
                device_fingerprint=json.dumps(device_info),
                ip_address=ip,
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            
            # Create device footprint
            DeviceFootprint.objects.create(
                session_attendance=attendance,
                screen_resolution=device_info.get('screen', ''),
                timezone=device_info.get('timezone', ''),
                language=device_info.get('language', ''),
                platform=device_info.get('platform', ''),
                browser_fingerprint=json.dumps(device_info)
            )
            
            return JsonResponse({
                'success': True,
                'message': f'Attendance recorded successfully for {attendee.full_name}',
                'attendee_name': attendee.full_name,
                'event_name': session.event.name,
                'session_info': f'Session {session.session_number} - {session.session_date}',
                'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
            })
            
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON data.'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'An error occurred: {str(e)}'
            })


@method_decorator(csrf_exempt, name='dispatch')
class RecordUnifiedAttendanceView(View):
    """Record attendance for events with dynamic checkpoint selection"""
    def post(self, request):
        try:
            data = json.loads(request.body)
            qr_code = data.get('qr_code')
            attendee_id = data.get('attendee_id')
            checkpoint_id = data.get('checkpoint_id')  # Can be None for simple attendance
            target_date = data.get('target_date')  # Optional, defaults to today
            device_info = data.get('device_info', {})
            
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
            
            if checkpoint_id:
                # Record checkpoint attendance
                try:
                    checkpoint = AttendanceCheckpoint.objects.get(
                        id=checkpoint_id, is_active=True
                    )
                    
                    # Verify checkpoint belongs to this event
                    if checkpoint.event != event and (not checkpoint.event_session or checkpoint.event_session.event != event):
                        return JsonResponse({
                            'success': False,
                            'error': 'Checkpoint does not belong to this event.'
                        })
                    
                    # Check if checkpoint applies to this date
                    if not checkpoint.applies_to_date(target_date):
                        return JsonResponse({
                            'success': False,
                            'error': f'This checkpoint does not apply to {target_date}.'
                        })
                    
                    # Check for existing checkpoint attendance
                    existing_checkpoint = CheckpointAttendance.objects.filter(
                        checkpoint=checkpoint,
                        attendee=attendee,
                        timestamp__date=target_date
                    ).first()
                    
                    if existing_checkpoint:
                        return JsonResponse({
                            'success': False,
                            'error': 'Attendance already recorded for this checkpoint today.'
                        })
                    
                    # Create checkpoint attendance
                    attendance = CheckpointAttendance.objects.create(
                        checkpoint=checkpoint,
                        attendee=attendee,
                        event=checkpoint.event,
                        event_session=checkpoint.event_session,
                        device_fingerprint=json.dumps(device_info),
                        ip_address=ip,
                        user_agent=request.META.get('HTTP_USER_AGENT', '')
                    )
                    
                    # Create device footprint
                    DeviceFootprint.objects.create(
                        checkpoint_attendance=attendance,
                        screen_resolution=device_info.get('screen', ''),
                        timezone=device_info.get('timezone', ''),
                        language=device_info.get('language', ''),
                        platform=device_info.get('platform', ''),
                        browser_fingerprint=json.dumps(device_info)
                    )
                    
                    # Determine status
                    status_message = "on time"
                    if attendance.is_late:
                        status_message = "late"
                    elif not attendance.is_on_time and not attendance.is_late:
                        status_message = "early"
                    
                    return JsonResponse({
                        'success': True,
                        'message': f'Checkpoint attendance recorded successfully ({status_message})',
                        'attendee_name': attendee.full_name,
                        'event_name': event.name,
                        'checkpoint_name': checkpoint.name,
                        'status': status_message,
                        'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    })
                    
                except AttendanceCheckpoint.DoesNotExist:
                    return JsonResponse({
                        'success': False,
                        'error': 'Invalid checkpoint.'
                    })
            else:
                # Record general event attendance
                if event.event_type == 'single':
                    # Check for existing attendance
                    if AttendanceRecord.objects.filter(event=event, attendee=attendee).exists():
                        return JsonResponse({
                            'success': False,
                            'error': 'Attendance already recorded for this event.'
                        })
                    
                    # Create attendance record
                    attendance = AttendanceRecord.objects.create(
                        event=event,
                        attendee=attendee,
                        device_fingerprint=json.dumps(device_info),
                        ip_address=ip,
                        user_agent=request.META.get('HTTP_USER_AGENT', '')
                    )
                    
                    # Create device footprint
                    DeviceFootprint.objects.create(
                        attendance_record=attendance,
                        screen_resolution=device_info.get('screen', ''),
                        timezone=device_info.get('timezone', ''),
                        language=device_info.get('language', ''),
                        platform=device_info.get('platform', ''),
                        browser_fingerprint=json.dumps(device_info)
                    )
                    
                    return JsonResponse({
                        'success': True,
                        'message': f'Attendance recorded successfully for {attendee.full_name}',
                        'attendee_name': attendee.full_name,
                        'event_name': event.name,
                        'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    })
                else:
                    # For multi-day events, find the session for target date
                    try:
                        session = event.eventsession_set.get(session_date=target_date)
                        
                        # Check for existing session attendance
                        if SessionAttendance.objects.filter(event_session=session, attendee=attendee).exists():
                            return JsonResponse({
                                'success': False,
                                'error': 'Attendance already recorded for this session.'
                            })
                        
                        # Create session attendance
                        attendance = SessionAttendance.objects.create(
                            event_session=session,
                            attendee=attendee,
                            device_fingerprint=json.dumps(device_info),
                            ip_address=ip,
                            user_agent=request.META.get('HTTP_USER_AGENT', '')
                        )
                        
                        # Create device footprint
                        DeviceFootprint.objects.create(
                            session_attendance=attendance,
                            screen_resolution=device_info.get('screen', ''),
                            timezone=device_info.get('timezone', ''),
                            language=device_info.get('language', ''),
                            platform=device_info.get('platform', ''),
                            browser_fingerprint=json.dumps(device_info)
                        )
                        
                        return JsonResponse({
                            'success': True,
                            'message': f'Session attendance recorded successfully for {attendee.full_name}',
                            'attendee_name': attendee.full_name,
                            'event_name': event.name,
                            'session_info': f'Session {session.session_number} - {session.session_date}',
                            'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                        })
                        
                    except:
                        return JsonResponse({
                            'success': False,
                            'error': f'No session found for {target_date}.'
                        })
            
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON data.'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'An error occurred: {str(e)}'
            })


class CheckpointScanView(TemplateView):
    template_name = 'attendance/checkpoint_scan.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        checkpoint_code = kwargs.get('checkpoint_code')
        
        try:
            checkpoint = AttendanceCheckpoint.objects.select_related('event', 'event_session').get(
                checkpoint_code=checkpoint_code, is_active=True
            )
            context['checkpoint'] = checkpoint
            context['event'] = checkpoint.event or checkpoint.event_session.event
            context['event_session'] = checkpoint.event_session
            context['valid_qr'] = True
            
            # Get current time to show if checkpoint is active
            from django.utils import timezone
            current_time = timezone.now().time()
            context['is_within_window'] = checkpoint.is_within_window(current_time)
            context['window_start'] = checkpoint.window_start
            context['window_end'] = checkpoint.window_end
            
        except AttendanceCheckpoint.DoesNotExist:
            context['valid_qr'] = False
            context['error'] = 'Invalid checkpoint QR code.'
        
        return context


@method_decorator(csrf_exempt, name='dispatch')
class RecordCheckpointAttendanceView(View):
    def post(self, request):
        try:
            data = json.loads(request.body)
            checkpoint_code = data.get('checkpoint_code')
            attendee_id = data.get('attendee_id')
            device_info = data.get('device_info', {})
            
            # Validate checkpoint
            try:
                checkpoint = AttendanceCheckpoint.objects.select_related('event', 'event_session').get(
                    checkpoint_code=checkpoint_code, is_active=True
                )
            except AttendanceCheckpoint.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid checkpoint QR code.'
                })
            
            # Validate attendee
            try:
                attendee = Attendee.objects.get(attendee_id=attendee_id, is_active=True)
            except Attendee.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid attendee ID.'
                })
            
            # Check if already attended this checkpoint
            existing_attendance = None
            if checkpoint.event:
                existing_attendance = CheckpointAttendance.objects.filter(
                    checkpoint=checkpoint, attendee=attendee, event=checkpoint.event
                ).first()
            elif checkpoint.event_session:
                existing_attendance = CheckpointAttendance.objects.filter(
                    checkpoint=checkpoint, attendee=attendee, event_session=checkpoint.event_session
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
            
            # Create checkpoint attendance record
            attendance = CheckpointAttendance.objects.create(
                checkpoint=checkpoint,
                attendee=attendee,
                event=checkpoint.event,
                event_session=checkpoint.event_session,
                device_fingerprint=json.dumps(device_info),
                ip_address=ip,
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            
            # Create device footprint
            DeviceFootprint.objects.create(
                checkpoint_attendance=attendance,
                screen_resolution=device_info.get('screen', ''),
                timezone=device_info.get('timezone', ''),
                language=device_info.get('language', ''),
                platform=device_info.get('platform', ''),
                browser_fingerprint=json.dumps(device_info)
            )
            
            # Determine status message
            status_message = "on time"
            if attendance.is_late:
                status_message = "late"
            elif not attendance.is_on_time and not attendance.is_late:
                status_message = "early"
            
            event_name = checkpoint.event.name if checkpoint.event else checkpoint.event_session.event.name
            
            return JsonResponse({
                'success': True,
                'message': f'Checkpoint attendance recorded successfully ({status_message})',
                'attendee_name': attendee.full_name,
                'event_name': event_name,
                'checkpoint_name': checkpoint.name,
                'checkpoint_time': checkpoint.required_time.strftime('%H:%M'),
                'status': status_message,
                'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
            })
            
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON data.'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'An error occurred: {str(e)}'
            })


@method_decorator(csrf_exempt, name='dispatch')
class RecordUnifiedAttendanceView(View):
    """Record attendance for events with dynamic checkpoint selection"""
    def post(self, request):
        try:
            data = json.loads(request.body)
            qr_code = data.get('qr_code')
            attendee_id = data.get('attendee_id')
            checkpoint_id = data.get('checkpoint_id')  # Can be None for simple attendance
            target_date = data.get('target_date')  # Optional, defaults to today
            device_info = data.get('device_info', {})
            
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
            
            if checkpoint_id:
                # Record checkpoint attendance
                try:
                    checkpoint = AttendanceCheckpoint.objects.get(
                        id=checkpoint_id, is_active=True
                    )
                    
                    # Verify checkpoint belongs to this event
                    if checkpoint.event != event and (not checkpoint.event_session or checkpoint.event_session.event != event):
                        return JsonResponse({
                            'success': False,
                            'error': 'Checkpoint does not belong to this event.'
                        })
                    
                    # Check if checkpoint applies to this date
                    if not checkpoint.applies_to_date(target_date):
                        return JsonResponse({
                            'success': False,
                            'error': f'This checkpoint does not apply to {target_date}.'
                        })
                    
                    # Check for existing checkpoint attendance
                    existing_checkpoint = CheckpointAttendance.objects.filter(
                        checkpoint=checkpoint,
                        attendee=attendee,
                        timestamp__date=target_date
                    ).first()
                    
                    if existing_checkpoint:
                        return JsonResponse({
                            'success': False,
                            'error': 'Attendance already recorded for this checkpoint today.'
                        })
                    
                    # Create checkpoint attendance
                    attendance = CheckpointAttendance.objects.create(
                        checkpoint=checkpoint,
                        attendee=attendee,
                        event=checkpoint.event,
                        event_session=checkpoint.event_session,
                        device_fingerprint=json.dumps(device_info),
                        ip_address=ip,
                        user_agent=request.META.get('HTTP_USER_AGENT', '')
                    )
                    
                    # Create device footprint
                    DeviceFootprint.objects.create(
                        checkpoint_attendance=attendance,
                        screen_resolution=device_info.get('screen', ''),
                        timezone=device_info.get('timezone', ''),
                        language=device_info.get('language', ''),
                        platform=device_info.get('platform', ''),
                        browser_fingerprint=json.dumps(device_info)
                    )
                    
                    # Determine status
                    status_message = "on time"
                    if attendance.is_late:
                        status_message = "late"
                    elif not attendance.is_on_time and not attendance.is_late:
                        status_message = "early"
                    
                    return JsonResponse({
                        'success': True,
                        'message': f'Checkpoint attendance recorded successfully ({status_message})',
                        'attendee_name': attendee.full_name,
                        'event_name': event.name,
                        'checkpoint_name': checkpoint.name,
                        'status': status_message,
                        'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    })
                    
                except AttendanceCheckpoint.DoesNotExist:
                    return JsonResponse({
                        'success': False,
                        'error': 'Invalid checkpoint.'
                    })
            else:
                # Record general event attendance
                if event.event_type == 'single':
                    # Check for existing attendance
                    if AttendanceRecord.objects.filter(event=event, attendee=attendee).exists():
                        return JsonResponse({
                            'success': False,
                            'error': 'Attendance already recorded for this event.'
                        })
                    
                    # Create attendance record
                    attendance = AttendanceRecord.objects.create(
                        event=event,
                        attendee=attendee,
                        device_fingerprint=json.dumps(device_info),
                        ip_address=ip,
                        user_agent=request.META.get('HTTP_USER_AGENT', '')
                    )
                    
                    # Create device footprint
                    DeviceFootprint.objects.create(
                        attendance_record=attendance,
                        screen_resolution=device_info.get('screen', ''),
                        timezone=device_info.get('timezone', ''),
                        language=device_info.get('language', ''),
                        platform=device_info.get('platform', ''),
                        browser_fingerprint=json.dumps(device_info)
                    )
                    
                    return JsonResponse({
                        'success': True,
                        'message': f'Attendance recorded successfully for {attendee.full_name}',
                        'attendee_name': attendee.full_name,
                        'event_name': event.name,
                        'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    })
                else:
                    # For multi-day events, find the session for target date
                    try:
                        session = event.eventsession_set.get(session_date=target_date)
                        
                        # Check for existing session attendance
                        if SessionAttendance.objects.filter(event_session=session, attendee=attendee).exists():
                            return JsonResponse({
                                'success': False,
                                'error': 'Attendance already recorded for this session.'
                            })
                        
                        # Create session attendance
                        attendance = SessionAttendance.objects.create(
                            event_session=session,
                            attendee=attendee,
                            device_fingerprint=json.dumps(device_info),
                            ip_address=ip,
                            user_agent=request.META.get('HTTP_USER_AGENT', '')
                        )
                        
                        # Create device footprint
                        DeviceFootprint.objects.create(
                            session_attendance=attendance,
                            screen_resolution=device_info.get('screen', ''),
                            timezone=device_info.get('timezone', ''),
                            language=device_info.get('language', ''),
                            platform=device_info.get('platform', ''),
                            browser_fingerprint=json.dumps(device_info)
                        )
                        
                        return JsonResponse({
                            'success': True,
                            'message': f'Session attendance recorded successfully for {attendee.full_name}',
                            'attendee_name': attendee.full_name,
                            'event_name': event.name,
                            'session_info': f'Session {session.session_number} - {session.session_date}',
                            'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                        })
                        
                    except:
                        return JsonResponse({
                            'success': False,
                            'error': f'No session found for {target_date}.'
                        })
            
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON data.'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'An error occurred: {str(e)}'
            })


@method_decorator(csrf_exempt, name='dispatch')
class GetEventCheckpointsView(View):
    def get(self, request, event_id):
        try:
            event = Event.objects.get(pk=event_id)
            checkpoints = AttendanceCheckpoint.objects.filter(
                event=event, is_active=True
            ).order_by('order')
            
            checkpoint_data = []
            for checkpoint in checkpoints:
                checkpoint_data.append({
                    'id': checkpoint.id,
                    'name': checkpoint.name,
                    'checkpoint_type': checkpoint.checkpoint_type,
                    'required_time': checkpoint.required_time.strftime('%H:%M'),
                    'window_start': checkpoint.window_start.strftime('%H:%M'),
                    'window_end': checkpoint.window_end.strftime('%H:%M'),
                    'order': checkpoint.order,
                    'checkpoint_code': checkpoint.checkpoint_code
                })
            
            return JsonResponse({
                'success': True,
                'checkpoints': checkpoint_data
            })
            
        except Event.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Event not found.'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'An error occurred: {str(e)}'
            })


@method_decorator(csrf_exempt, name='dispatch')
class RecordUnifiedAttendanceView(View):
    """Record attendance for events with dynamic checkpoint selection"""
    def post(self, request):
        try:
            data = json.loads(request.body)
            qr_code = data.get('qr_code')
            attendee_id = data.get('attendee_id')
            checkpoint_id = data.get('checkpoint_id')  # Can be None for simple attendance
            target_date = data.get('target_date')  # Optional, defaults to today
            device_info = data.get('device_info', {})
            
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
            
            if checkpoint_id:
                # Record checkpoint attendance
                try:
                    checkpoint = AttendanceCheckpoint.objects.get(
                        id=checkpoint_id, is_active=True
                    )
                    
                    # Verify checkpoint belongs to this event
                    if checkpoint.event != event and (not checkpoint.event_session or checkpoint.event_session.event != event):
                        return JsonResponse({
                            'success': False,
                            'error': 'Checkpoint does not belong to this event.'
                        })
                    
                    # Check if checkpoint applies to this date
                    if not checkpoint.applies_to_date(target_date):
                        return JsonResponse({
                            'success': False,
                            'error': f'This checkpoint does not apply to {target_date}.'
                        })
                    
                    # Check for existing checkpoint attendance
                    existing_checkpoint = CheckpointAttendance.objects.filter(
                        checkpoint=checkpoint,
                        attendee=attendee,
                        timestamp__date=target_date
                    ).first()
                    
                    if existing_checkpoint:
                        return JsonResponse({
                            'success': False,
                            'error': 'Attendance already recorded for this checkpoint today.'
                        })
                    
                    # Create checkpoint attendance
                    attendance = CheckpointAttendance.objects.create(
                        checkpoint=checkpoint,
                        attendee=attendee,
                        event=checkpoint.event,
                        event_session=checkpoint.event_session,
                        device_fingerprint=json.dumps(device_info),
                        ip_address=ip,
                        user_agent=request.META.get('HTTP_USER_AGENT', '')
                    )
                    
                    # Create device footprint
                    DeviceFootprint.objects.create(
                        checkpoint_attendance=attendance,
                        screen_resolution=device_info.get('screen', ''),
                        timezone=device_info.get('timezone', ''),
                        language=device_info.get('language', ''),
                        platform=device_info.get('platform', ''),
                        browser_fingerprint=json.dumps(device_info)
                    )
                    
                    # Determine status
                    status_message = "on time"
                    if attendance.is_late:
                        status_message = "late"
                    elif not attendance.is_on_time and not attendance.is_late:
                        status_message = "early"
                    
                    return JsonResponse({
                        'success': True,
                        'message': f'Checkpoint attendance recorded successfully ({status_message})',
                        'attendee_name': attendee.full_name,
                        'event_name': event.name,
                        'checkpoint_name': checkpoint.name,
                        'status': status_message,
                        'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    })
                    
                except AttendanceCheckpoint.DoesNotExist:
                    return JsonResponse({
                        'success': False,
                        'error': 'Invalid checkpoint.'
                    })
            else:
                # Record general event attendance
                if event.event_type == 'single':
                    # Check for existing attendance
                    if AttendanceRecord.objects.filter(event=event, attendee=attendee).exists():
                        return JsonResponse({
                            'success': False,
                            'error': 'Attendance already recorded for this event.'
                        })
                    
                    # Create attendance record
                    attendance = AttendanceRecord.objects.create(
                        event=event,
                        attendee=attendee,
                        device_fingerprint=json.dumps(device_info),
                        ip_address=ip,
                        user_agent=request.META.get('HTTP_USER_AGENT', '')
                    )
                    
                    # Create device footprint
                    DeviceFootprint.objects.create(
                        attendance_record=attendance,
                        screen_resolution=device_info.get('screen', ''),
                        timezone=device_info.get('timezone', ''),
                        language=device_info.get('language', ''),
                        platform=device_info.get('platform', ''),
                        browser_fingerprint=json.dumps(device_info)
                    )
                    
                    return JsonResponse({
                        'success': True,
                        'message': f'Attendance recorded successfully for {attendee.full_name}',
                        'attendee_name': attendee.full_name,
                        'event_name': event.name,
                        'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    })
                else:
                    # For multi-day events, find the session for target date
                    try:
                        session = event.eventsession_set.get(session_date=target_date)
                        
                        # Check for existing session attendance
                        if SessionAttendance.objects.filter(event_session=session, attendee=attendee).exists():
                            return JsonResponse({
                                'success': False,
                                'error': 'Attendance already recorded for this session.'
                            })
                        
                        # Create session attendance
                        attendance = SessionAttendance.objects.create(
                            event_session=session,
                            attendee=attendee,
                            device_fingerprint=json.dumps(device_info),
                            ip_address=ip,
                            user_agent=request.META.get('HTTP_USER_AGENT', '')
                        )
                        
                        # Create device footprint
                        DeviceFootprint.objects.create(
                            session_attendance=attendance,
                            screen_resolution=device_info.get('screen', ''),
                            timezone=device_info.get('timezone', ''),
                            language=device_info.get('language', ''),
                            platform=device_info.get('platform', ''),
                            browser_fingerprint=json.dumps(device_info)
                        )
                        
                        return JsonResponse({
                            'success': True,
                            'message': f'Session attendance recorded successfully for {attendee.full_name}',
                            'attendee_name': attendee.full_name,
                            'event_name': event.name,
                            'session_info': f'Session {session.session_number} - {session.session_date}',
                            'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                        })
                        
                    except:
                        return JsonResponse({
                            'success': False,
                            'error': f'No session found for {target_date}.'
                        })
            
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON data.'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'An error occurred: {str(e)}'
            })


@method_decorator(csrf_exempt, name='dispatch')
class GetSessionCheckpointsView(View):
    def get(self, request, session_id):
        try:
            session = EventSession.objects.get(pk=session_id)
            checkpoints = AttendanceCheckpoint.objects.filter(
                event_session=session, is_active=True
            ).order_by('order')
            
            checkpoint_data = []
            for checkpoint in checkpoints:
                checkpoint_data.append({
                    'id': checkpoint.id,
                    'name': checkpoint.name,
                    'checkpoint_type': checkpoint.checkpoint_type,
                    'required_time': checkpoint.required_time.strftime('%H:%M'),
                    'window_start': checkpoint.window_start.strftime('%H:%M'),
                    'window_end': checkpoint.window_end.strftime('%H:%M'),
                    'order': checkpoint.order,
                    'checkpoint_code': checkpoint.checkpoint_code
                })
            
            return JsonResponse({
                'success': True,
                'checkpoints': checkpoint_data
            })
            
        except EventSession.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Session not found.'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'An error occurred: {str(e)}'
            })


@method_decorator(csrf_exempt, name='dispatch')
class RecordUnifiedAttendanceView(View):
    """Record attendance for events with dynamic checkpoint selection"""
    def post(self, request):
        try:
            data = json.loads(request.body)
            qr_code = data.get('qr_code')
            attendee_id = data.get('attendee_id')
            checkpoint_id = data.get('checkpoint_id')  # Can be None for simple attendance
            target_date = data.get('target_date')  # Optional, defaults to today
            device_info = data.get('device_info', {})
            
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
            
            if checkpoint_id:
                # Record checkpoint attendance
                try:
                    checkpoint = AttendanceCheckpoint.objects.get(
                        id=checkpoint_id, is_active=True
                    )
                    
                    # Verify checkpoint belongs to this event
                    if checkpoint.event != event and (not checkpoint.event_session or checkpoint.event_session.event != event):
                        return JsonResponse({
                            'success': False,
                            'error': 'Checkpoint does not belong to this event.'
                        })
                    
                    # Check if checkpoint applies to this date
                    if not checkpoint.applies_to_date(target_date):
                        return JsonResponse({
                            'success': False,
                            'error': f'This checkpoint does not apply to {target_date}.'
                        })
                    
                    # Check for existing checkpoint attendance
                    existing_checkpoint = CheckpointAttendance.objects.filter(
                        checkpoint=checkpoint,
                        attendee=attendee,
                        timestamp__date=target_date
                    ).first()
                    
                    if existing_checkpoint:
                        return JsonResponse({
                            'success': False,
                            'error': 'Attendance already recorded for this checkpoint today.'
                        })
                    
                    # Create checkpoint attendance
                    attendance = CheckpointAttendance.objects.create(
                        checkpoint=checkpoint,
                        attendee=attendee,
                        event=checkpoint.event,
                        event_session=checkpoint.event_session,
                        device_fingerprint=json.dumps(device_info),
                        ip_address=ip,
                        user_agent=request.META.get('HTTP_USER_AGENT', '')
                    )
                    
                    # Create device footprint
                    DeviceFootprint.objects.create(
                        checkpoint_attendance=attendance,
                        screen_resolution=device_info.get('screen', ''),
                        timezone=device_info.get('timezone', ''),
                        language=device_info.get('language', ''),
                        platform=device_info.get('platform', ''),
                        browser_fingerprint=json.dumps(device_info)
                    )
                    
                    # Determine status
                    status_message = "on time"
                    if attendance.is_late:
                        status_message = "late"
                    elif not attendance.is_on_time and not attendance.is_late:
                        status_message = "early"
                    
                    return JsonResponse({
                        'success': True,
                        'message': f'Checkpoint attendance recorded successfully ({status_message})',
                        'attendee_name': attendee.full_name,
                        'event_name': event.name,
                        'checkpoint_name': checkpoint.name,
                        'status': status_message,
                        'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    })
                    
                except AttendanceCheckpoint.DoesNotExist:
                    return JsonResponse({
                        'success': False,
                        'error': 'Invalid checkpoint.'
                    })
            else:
                # Record general event attendance
                if event.event_type == 'single':
                    # Check for existing attendance
                    if AttendanceRecord.objects.filter(event=event, attendee=attendee).exists():
                        return JsonResponse({
                            'success': False,
                            'error': 'Attendance already recorded for this event.'
                        })
                    
                    # Create attendance record
                    attendance = AttendanceRecord.objects.create(
                        event=event,
                        attendee=attendee,
                        device_fingerprint=json.dumps(device_info),
                        ip_address=ip,
                        user_agent=request.META.get('HTTP_USER_AGENT', '')
                    )
                    
                    # Create device footprint
                    DeviceFootprint.objects.create(
                        attendance_record=attendance,
                        screen_resolution=device_info.get('screen', ''),
                        timezone=device_info.get('timezone', ''),
                        language=device_info.get('language', ''),
                        platform=device_info.get('platform', ''),
                        browser_fingerprint=json.dumps(device_info)
                    )
                    
                    return JsonResponse({
                        'success': True,
                        'message': f'Attendance recorded successfully for {attendee.full_name}',
                        'attendee_name': attendee.full_name,
                        'event_name': event.name,
                        'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    })
                else:
                    # For multi-day events, find the session for target date
                    try:
                        session = event.eventsession_set.get(session_date=target_date)
                        
                        # Check for existing session attendance
                        if SessionAttendance.objects.filter(event_session=session, attendee=attendee).exists():
                            return JsonResponse({
                                'success': False,
                                'error': 'Attendance already recorded for this session.'
                            })
                        
                        # Create session attendance
                        attendance = SessionAttendance.objects.create(
                            event_session=session,
                            attendee=attendee,
                            device_fingerprint=json.dumps(device_info),
                            ip_address=ip,
                            user_agent=request.META.get('HTTP_USER_AGENT', '')
                        )
                        
                        # Create device footprint
                        DeviceFootprint.objects.create(
                            session_attendance=attendance,
                            screen_resolution=device_info.get('screen', ''),
                            timezone=device_info.get('timezone', ''),
                            language=device_info.get('language', ''),
                            platform=device_info.get('platform', ''),
                            browser_fingerprint=json.dumps(device_info)
                        )
                        
                        return JsonResponse({
                            'success': True,
                            'message': f'Session attendance recorded successfully for {attendee.full_name}',
                            'attendee_name': attendee.full_name,
                            'event_name': event.name,
                            'session_info': f'Session {session.session_number} - {session.session_date}',
                            'timestamp': attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                        })
                        
                    except:
                        return JsonResponse({
                            'success': False,
                            'error': f'No session found for {target_date}.'
                        })
            
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON data.'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'An error occurred: {str(e)}'
            })
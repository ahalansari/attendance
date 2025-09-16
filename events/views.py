from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, CreateView, DetailView, UpdateView, TemplateView, FormView, View
from django.urls import reverse_lazy
from django.http import HttpResponse, JsonResponse
from django.conf import settings
import qrcode
from io import BytesIO
import base64
from .models import Event, EventSession
from .forms import EventForm, EventSessionForm
from attendance.models import AttendanceRecord, SessionAttendance, AttendanceCheckpoint, CheckpointAttendance
from attendance.forms import AttendanceCheckpointForm, QuickCheckpointForm


class EventListView(LoginRequiredMixin, ListView):
    model = Event
    template_name = 'events/list.html'
    context_object_name = 'events'
    paginate_by = 20

    def get_queryset(self):
        return Event.objects.filter(is_active=True).order_by('-date', '-start_time')


class EventCreateView(LoginRequiredMixin, CreateView):
    model = Event
    form_class = EventForm
    template_name = 'events/create.html'
    success_url = reverse_lazy('events:list')

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        
        # Generate sessions for multi-date events
        if form.instance.event_type in ['span', 'recurring']:
            form.instance.generate_sessions()
            
        return response


class EventDetailView(LoginRequiredMixin, DetailView):
    model = Event
    template_name = 'events/detail.html'
    context_object_name = 'event'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get attendance records and sessions
        context['attendance_records'] = AttendanceRecord.objects.filter(
            event=self.object
        ).select_related('attendee').order_by('-timestamp')
        
        context['event_sessions'] = EventSession.objects.filter(
            event=self.object
        ).order_by('session_date')
        
        # Get session attendance for multi-date events
        if self.object.event_type in ['span', 'recurring']:
            context['session_attendance'] = SessionAttendance.objects.filter(
                event_session__event=self.object
            ).select_related('attendee', 'event_session').order_by('-timestamp')
        
        return context


class EventUpdateView(LoginRequiredMixin, UpdateView):
    model = Event
    form_class = EventForm
    template_name = 'events/edit.html'
    success_url = reverse_lazy('events:list')


class EventQRView(LoginRequiredMixin, TemplateView):
    template_name = 'events/qr.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        event = get_object_or_404(Event, pk=kwargs['pk'])
        
        # Generate QR code
        qr_data = f"{settings.SITE_URL}/scan/{event.qr_code}/"
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(qr_data)
        qr.make(fit=True)
        
        # Create QR code image
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        qr_image = base64.b64encode(buffer.getvalue()).decode()
        
        context['event'] = event
        context['qr_image'] = qr_image
        context['qr_url'] = qr_data
        return context


class EventPrintView(LoginRequiredMixin, TemplateView):
    template_name = 'events/print.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        event = get_object_or_404(Event, pk=kwargs['pk'])
        
        # Generate QR code
        qr_data = f"{settings.SITE_URL}/scan/{event.qr_code}/"
        qr = qrcode.QRCode(version=1, box_size=15, border=5)
        qr.add_data(qr_data)
        qr.make(fit=True)
        
        # Create QR code image
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        qr_image = base64.b64encode(buffer.getvalue()).decode()
        
        context['event'] = event
        context['qr_image'] = qr_image
        return context


class EventAttendeesView(LoginRequiredMixin, DetailView):
    model = Event
    template_name = 'events/attendees.html'
    context_object_name = 'event'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['attendance_records'] = AttendanceRecord.objects.filter(
            event=self.object
        ).select_related('attendee').order_by('attendee__attendee_id')
        return context


class EventSessionsView(LoginRequiredMixin, DetailView):
    model = Event
    template_name = 'events/sessions.html'
    context_object_name = 'event'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sessions'] = EventSession.objects.filter(
            event=self.object
        ).order_by('session_date')
        return context


class CreateSessionView(LoginRequiredMixin, CreateView):
    model = EventSession
    form_class = EventSessionForm
    template_name = 'events/create_session.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['event'] = get_object_or_404(Event, pk=self.kwargs['pk'])
        return context

    def form_valid(self, form):
        event = get_object_or_404(Event, pk=self.kwargs['pk'])
        form.instance.event = event
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('events:sessions', kwargs={'pk': self.kwargs['pk']})


class SessionQRView(LoginRequiredMixin, TemplateView):
    template_name = 'events/session_qr.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session = get_object_or_404(EventSession, pk=kwargs['pk'])
        
        # Generate QR code for session
        qr_data = f"{settings.SITE_URL}/scan/session/{session.qr_code}/"
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(qr_data)
        qr.make(fit=True)
        
        # Create QR code image
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        qr_image = base64.b64encode(buffer.getvalue()).decode()
        
        context['session'] = session
        context['event'] = session.event
        context['qr_image'] = qr_image
        context['qr_url'] = qr_data
        return context


class SessionPrintView(LoginRequiredMixin, TemplateView):
    template_name = 'events/session_print.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session = get_object_or_404(EventSession, pk=kwargs['pk'])
        
        # Generate QR code for session
        qr_data = f"{settings.SITE_URL}/scan/session/{session.qr_code}/"
        qr = qrcode.QRCode(version=1, box_size=15, border=5)
        qr.add_data(qr_data)
        qr.make(fit=True)
        
        # Create QR code image
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        qr_image = base64.b64encode(buffer.getvalue()).decode()
        
        context['session'] = session
        context['event'] = session.event
        context['qr_image'] = qr_image
        return context


class EventCheckpointsView(LoginRequiredMixin, DetailView):
    model = Event
    template_name = 'events/checkpoints.html'
    context_object_name = 'event'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['checkpoints'] = AttendanceCheckpoint.objects.filter(
            event=self.object, is_active=True
        ).order_by('order')
        return context


class CreateCheckpointView(LoginRequiredMixin, CreateView):
    model = AttendanceCheckpoint
    form_class = AttendanceCheckpointForm
    template_name = 'events/create_checkpoint.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['event'] = get_object_or_404(Event, pk=self.kwargs['pk'])
        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['event'] = get_object_or_404(Event, pk=self.kwargs['pk'])
        return kwargs

    def form_valid(self, form):
        event = get_object_or_404(Event, pk=self.kwargs['pk'])
        form.instance.event = event
        form.instance.created_by = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('events:checkpoints', kwargs={'pk': self.kwargs['pk']})


class QuickSetupCheckpointsView(LoginRequiredMixin, FormView):
    form_class = QuickCheckpointForm
    template_name = 'events/quick_checkpoints.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['event'] = get_object_or_404(Event, pk=self.kwargs['pk'])
        return context

    def form_valid(self, form):
        event = get_object_or_404(Event, pk=self.kwargs['pk'])
        pattern = form.cleaned_data['pattern']
        grace_period = form.cleaned_data['grace_period']
        
        # Clear existing checkpoints
        AttendanceCheckpoint.objects.filter(event=event).delete()
        
        if pattern == 'entrance_exit':
            self._create_entrance_exit_checkpoints(event, grace_period)
        elif pattern == 'hourly':
            self._create_hourly_checkpoints(event, form.cleaned_data, grace_period)
        elif pattern == 'entrance_lunch_exit':
            self._create_entrance_lunch_exit_checkpoints(event, form.cleaned_data, grace_period)
        elif pattern == 'entrance_breaks_exit':
            self._create_entrance_breaks_exit_checkpoints(event, form.cleaned_data, grace_period)
        
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('events:checkpoints', kwargs={'pk': self.kwargs['pk']})

    def _create_entrance_exit_checkpoints(self, event, grace_period):
        AttendanceCheckpoint.objects.create(
            event=event,
            checkpoint_type='entrance',
            name='Entrance Check',
            required_time=event.start_time,
            grace_period_minutes=grace_period,
            order=1,
            created_by=self.request.user
        )
        AttendanceCheckpoint.objects.create(
            event=event,
            checkpoint_type='exit',
            name='Exit Check',
            required_time=event.end_time,
            grace_period_minutes=grace_period,
            order=2,
            created_by=self.request.user
        )

    def _create_hourly_checkpoints(self, event, data, grace_period):
        from datetime import datetime, timedelta
        start_time = data['start_time']
        end_time = data['end_time']
        
        current_time = datetime.combine(datetime.today(), start_time)
        end_datetime = datetime.combine(datetime.today(), end_time)
        order = 1
        
        while current_time <= end_datetime:
            AttendanceCheckpoint.objects.create(
                event=event,
                checkpoint_type='hourly',
                name=f'{current_time.strftime("%H:%M")} Check',
                required_time=current_time.time(),
                grace_period_minutes=grace_period,
                order=order,
                created_by=self.request.user
            )
            current_time += timedelta(hours=1)
            order += 1

    def _create_entrance_lunch_exit_checkpoints(self, event, data, grace_period):
        lunch_time = data.get('lunch_time')
        
        AttendanceCheckpoint.objects.create(
            event=event,
            checkpoint_type='entrance',
            name='Entrance Check',
            required_time=event.start_time,
            grace_period_minutes=grace_period,
            order=1,
            created_by=self.request.user
        )
        
        if lunch_time:
            AttendanceCheckpoint.objects.create(
                event=event,
                checkpoint_type='lunch',
                name='Lunch Break',
                required_time=lunch_time,
                grace_period_minutes=grace_period,
                order=2,
                created_by=self.request.user
            )
        
        AttendanceCheckpoint.objects.create(
            event=event,
            checkpoint_type='exit',
            name='Exit Check',
            required_time=event.end_time,
            grace_period_minutes=grace_period,
            order=3,
            created_by=self.request.user
        )

    def _create_entrance_breaks_exit_checkpoints(self, event, data, grace_period):
        morning_break = data.get('morning_break')
        lunch_time = data.get('lunch_time')
        afternoon_break = data.get('afternoon_break')
        
        order = 1
        
        AttendanceCheckpoint.objects.create(
            event=event,
            checkpoint_type='entrance',
            name='Entrance Check',
            required_time=event.start_time,
            grace_period_minutes=grace_period,
            order=order,
            created_by=self.request.user
        )
        order += 1
        
        if morning_break:
            AttendanceCheckpoint.objects.create(
                event=event,
                checkpoint_type='break',
                name='Morning Break',
                required_time=morning_break,
                grace_period_minutes=grace_period,
                order=order,
                created_by=self.request.user
            )
            order += 1
        
        if lunch_time:
            AttendanceCheckpoint.objects.create(
                event=event,
                checkpoint_type='lunch',
                name='Lunch Break',
                required_time=lunch_time,
                grace_period_minutes=grace_period,
                order=order,
                created_by=self.request.user
            )
            order += 1
        
        if afternoon_break:
            AttendanceCheckpoint.objects.create(
                event=event,
                checkpoint_type='break',
                name='Afternoon Break',
                required_time=afternoon_break,
                grace_period_minutes=grace_period,
                order=order,
                created_by=self.request.user
            )
            order += 1
        
        AttendanceCheckpoint.objects.create(
            event=event,
            checkpoint_type='exit',
            name='Exit Check',
            required_time=event.end_time,
            grace_period_minutes=grace_period,
            order=order,
            created_by=self.request.user
        )


class BatchGenerateCheckpointsView(LoginRequiredMixin, TemplateView):
    template_name = 'events/batch_generate_checkpoints.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['event'] = get_object_or_404(Event, pk=self.kwargs['pk'])
        return context

    def post(self, request, pk):
        event = get_object_or_404(Event, pk=pk)
        
        # Get form data
        checkpoint_template_ids = request.POST.getlist('checkpoint_templates')
        date_option = request.POST.get('date_option', 'all')
        generate_for_all_days = date_option == 'all'
        selected_dates = request.POST.getlist('selected_dates')
        
        if not checkpoint_template_ids:
            return JsonResponse({'success': False, 'error': 'No checkpoint templates selected.'})
        
        # Get checkpoint templates (existing event-level checkpoints)
        checkpoint_templates = AttendanceCheckpoint.objects.filter(
            id__in=checkpoint_template_ids, event=event
        )
        
        if not checkpoint_templates.exists():
            return JsonResponse({'success': False, 'error': 'Invalid checkpoint templates.'})
        
        # Determine target dates
        target_dates = []
        available_dates = event.get_available_dates()
        
        if generate_for_all_days:
            target_dates = available_dates
        else:
            from datetime import datetime
            for date_str in selected_dates:
                try:
                    date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                    if date_obj in available_dates:
                        target_dates.append(date_obj)
                except ValueError:
                    continue
        
        if not target_dates:
            return JsonResponse({
                'success': False, 
                'error': f'No valid dates selected. Available dates: {[str(d) for d in available_dates]}. Generate all days: {generate_for_all_days}. Selected dates: {selected_dates}'
            })
        
        # Generate checkpoints for each date
        created_count = 0
        for target_date in target_dates:
            try:
                # Get or create session for this date (for multi-day events)
                session = None
                if event.event_type != 'single':
                    session = event.eventsession_set.get(session_date=target_date)
                
                for template in checkpoint_templates:
                    # Check if checkpoint already exists for this date
                    existing = None
                    if session:
                        existing = AttendanceCheckpoint.objects.filter(
                            event_session=session,
                            checkpoint_type=template.checkpoint_type,
                            required_time=template.required_time
                        ).first()
                    else:
                        # For single events, check by date in the name or specific_date
                        existing = AttendanceCheckpoint.objects.filter(
                            event=event,
                            event_session__isnull=True,
                            checkpoint_type=template.checkpoint_type,
                            required_time=template.required_time,
                            specific_date=target_date
                        ).first()
                    
                    if not existing:
                        # Create new checkpoint
                        checkpoint_name = template.name
                        if len(target_dates) > 1:
                            checkpoint_name = f"{template.name} ({target_date})"
                        
                        AttendanceCheckpoint.objects.create(
                            event=event if event.event_type == 'single' else None,
                            event_session=session,
                            checkpoint_type=template.checkpoint_type,
                            name=checkpoint_name,
                            description=template.description,
                            required_time=template.required_time,
                            grace_period_minutes=template.grace_period_minutes,
                            is_required=template.is_required,
                            order=template.order,
                            applies_to='specific_day' if len(target_dates) > 1 else 'all_days',
                            specific_date=target_date if len(target_dates) > 1 else None,
                            created_by=request.user
                        )
                        created_count += 1
                        
            except Exception as e:
                continue
        
        return JsonResponse({
            'success': True,
            'message': f'Successfully created {created_count} checkpoints across {len(target_dates)} dates.',
            'created_count': created_count,
            'target_dates_count': len(target_dates)
        })


class SessionCheckpointsView(LoginRequiredMixin, DetailView):
    model = EventSession
    template_name = 'events/session_checkpoints.html'
    context_object_name = 'session'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['event'] = self.object.event
        context['checkpoints'] = AttendanceCheckpoint.objects.filter(
            event_session=self.object, is_active=True
        ).order_by('order')
        return context


class CreateSessionCheckpointView(LoginRequiredMixin, CreateView):
    model = AttendanceCheckpoint
    form_class = AttendanceCheckpointForm
    template_name = 'events/create_session_checkpoint.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session = get_object_or_404(EventSession, pk=self.kwargs['pk'])
        context['session'] = session
        context['event'] = session.event
        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['event_session'] = get_object_or_404(EventSession, pk=self.kwargs['pk'])
        return kwargs

    def form_valid(self, form):
        session = get_object_or_404(EventSession, pk=self.kwargs['pk'])
        form.instance.event_session = session
        form.instance.created_by = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('events:session_checkpoints', kwargs={'pk': self.kwargs['pk']})


class EditCheckpointView(LoginRequiredMixin, UpdateView):
    model = AttendanceCheckpoint
    form_class = AttendanceCheckpointForm
    template_name = 'events/edit_checkpoint.html'

    def get_success_url(self):
        if self.object.event:
            return reverse_lazy('events:checkpoints', kwargs={'pk': self.object.event.pk})
        else:
            return reverse_lazy('events:session_checkpoints', kwargs={'pk': self.object.event_session.pk})


class DeleteCheckpointView(LoginRequiredMixin, View):
    def post(self, request, pk):
        checkpoint = get_object_or_404(AttendanceCheckpoint, pk=pk)
        event_pk = checkpoint.event.pk if checkpoint.event else None
        session_pk = checkpoint.event_session.pk if checkpoint.event_session else None
        
        checkpoint.delete()
        
        if event_pk:
            return redirect('events:checkpoints', pk=event_pk)
        else:
            return redirect('events:session_checkpoints', pk=session_pk)
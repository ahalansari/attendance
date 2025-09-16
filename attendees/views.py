from django.shortcuts import render, redirect
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, CreateView, DetailView, UpdateView, TemplateView
from django.urls import reverse_lazy
from django.contrib import messages
from django.http import JsonResponse
from django.db import models
from .models import Attendee
from .forms import AttendeeForm, BulkImportForm
from attendance.models import AttendanceRecord


class AttendeeListView(LoginRequiredMixin, ListView):
    model = Attendee
    template_name = 'attendees/list.html'
    context_object_name = 'attendees'
    paginate_by = 50

    def get_queryset(self):
        queryset = Attendee.objects.filter(is_active=True).order_by('attendee_id')
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                models.Q(attendee_id__icontains=search) |
                models.Q(first_name__icontains=search) |
                models.Q(last_name__icontains=search) |
                models.Q(email__icontains=search)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search'] = self.request.GET.get('search', '')
        return context


class AttendeeCreateView(LoginRequiredMixin, CreateView):
    model = Attendee
    form_class = AttendeeForm
    template_name = 'attendees/create.html'
    success_url = reverse_lazy('attendees:list')

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class AttendeeDetailView(LoginRequiredMixin, DetailView):
    model = Attendee
    template_name = 'attendees/detail.html'
    context_object_name = 'attendee'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['attendance_records'] = AttendanceRecord.objects.filter(
            attendee=self.object
        ).select_related('event').order_by('-timestamp')
        return context


class AttendeeUpdateView(LoginRequiredMixin, UpdateView):
    model = Attendee
    form_class = AttendeeForm
    template_name = 'attendees/edit.html'
    success_url = reverse_lazy('attendees:list')


class BulkImportView(LoginRequiredMixin, TemplateView):
    template_name = 'attendees/bulk_import.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = BulkImportForm()
        return context

    def post(self, request, *args, **kwargs):
        form = BulkImportForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                imported_count = form.save(request.user)
                messages.success(request, f"Successfully imported {imported_count} attendees.")
                return redirect('attendees:list')
            except Exception as e:
                messages.error(request, f"Error importing attendees: {str(e)}")
        
        context = self.get_context_data(**kwargs)
        context['form'] = form
        return self.render_to_response(context)
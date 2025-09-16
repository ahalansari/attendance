#!/usr/bin/env python
"""
Sample data population script for QR Attendance System
Run this after setting up the database to populate with test data.
"""

import os
import django
from datetime import datetime, timedelta
import random

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'attendance_system.settings')
django.setup()

from django.contrib.auth.models import User
from events.models import Event
from attendees.models import Attendee
from attendance.models import AttendanceRecord, DeviceFootprint
import json

def create_sample_data():
    """Create sample events, attendees, and attendance records"""
    
    # Get or create admin user
    admin_user, created = User.objects.get_or_create(
        username='admin',
        defaults={
            'email': 'admin@example.com',
            'is_staff': True,
            'is_superuser': True
        }
    )
    if created:
        admin_user.set_password('admin123')
        admin_user.save()
        print("Created admin user")

    # Create sample events
    events_data = [
        {
            'name': 'Tech Conference 2024',
            'description': 'Annual technology conference with industry leaders',
            'date': datetime.now().date() + timedelta(days=1),
            'start_time': '09:00',
            'end_time': '17:00',
            'location': 'Convention Center Hall A'
        },
        {
            'name': 'Python Workshop',
            'description': 'Hands-on Python programming workshop',
            'date': datetime.now().date() + timedelta(days=3),
            'start_time': '14:00',
            'end_time': '18:00',
            'location': 'Training Room 101'
        },
        {
            'name': 'Networking Meetup',
            'description': 'Monthly professional networking event',
            'date': datetime.now().date() + timedelta(days=7),
            'start_time': '18:30',
            'end_time': '21:00',
            'location': 'Sky Lounge'
        },
        {
            'name': 'AI & Machine Learning Summit',
            'description': 'Latest trends in AI and ML',
            'date': datetime.now().date() - timedelta(days=2),
            'start_time': '10:00',
            'end_time': '16:00',
            'location': 'Innovation Hub'
        }
    ]

    created_events = []
    for event_data in events_data:
        event, created = Event.objects.get_or_create(
            name=event_data['name'],
            defaults={
                **event_data,
                'created_by': admin_user
            }
        )
        if created:
            created_events.append(event)
            print(f"Created event: {event.name}")

    # Create sample attendees
    attendees_data = [
        {'first_name': 'John', 'last_name': 'Smith', 'email': 'john.smith@email.com', 'phone': '+1234567890'},
        {'first_name': 'Jane', 'last_name': 'Doe', 'email': 'jane.doe@email.com', 'phone': '+1234567891'},
        {'first_name': 'Mike', 'last_name': 'Johnson', 'email': 'mike.johnson@email.com', 'phone': '+1234567892'},
        {'first_name': 'Sarah', 'last_name': 'Wilson', 'email': 'sarah.wilson@email.com', 'phone': '+1234567893'},
        {'first_name': 'David', 'last_name': 'Brown', 'email': 'david.brown@email.com', 'phone': '+1234567894'},
        {'first_name': 'Emily', 'last_name': 'Davis', 'email': 'emily.davis@email.com', 'phone': '+1234567895'},
        {'first_name': 'Chris', 'last_name': 'Martinez', 'email': 'chris.martinez@email.com', 'phone': '+1234567896'},
        {'first_name': 'Lisa', 'last_name': 'Anderson', 'email': 'lisa.anderson@email.com', 'phone': '+1234567897'},
        {'first_name': 'Tom', 'last_name': 'Taylor', 'email': 'tom.taylor@email.com', 'phone': '+1234567898'},
        {'first_name': 'Anna', 'last_name': 'Thomas', 'email': 'anna.thomas@email.com', 'phone': '+1234567899'}
    ]

    created_attendees = []
    for attendee_data in attendees_data:
        attendee, created = Attendee.objects.get_or_create(
            email=attendee_data['email'],
            defaults={
                **attendee_data,
                'created_by': admin_user
            }
        )
        if created:
            created_attendees.append(attendee)
            print(f"Created attendee: {attendee.full_name} (ID: {attendee.attendee_id})")

    # Create sample attendance records for past events
    past_events = Event.objects.filter(date__lt=datetime.now().date())
    sample_device_info = {
        'screen': '1920x1080',
        'timezone': 'America/New_York',
        'language': 'en-US',
        'platform': 'MacIntel',
    }

    for event in past_events:
        # Randomly select attendees for each event
        num_attendees = random.randint(3, 8)
        event_attendees = random.sample(list(Attendee.objects.all()), min(num_attendees, Attendee.objects.count()))
        
        for attendee in event_attendees:
            # Check if attendance record already exists
            if not AttendanceRecord.objects.filter(event=event, attendee=attendee).exists():
                # Create attendance record
                attendance = AttendanceRecord.objects.create(
                    event=event,
                    attendee=attendee,
                    device_fingerprint=json.dumps(sample_device_info),
                    ip_address='192.168.1.100',
                    user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
                )
                
                # Create device footprint
                DeviceFootprint.objects.create(
                    attendance_record=attendance,
                    screen_resolution=sample_device_info['screen'],
                    timezone=sample_device_info['timezone'],
                    language=sample_device_info['language'],
                    platform=sample_device_info['platform'],
                    browser_fingerprint=json.dumps(sample_device_info)
                )
                
                print(f"Created attendance record: {attendee.full_name} -> {event.name}")

    print("\nSample data population completed!")
    print("\nLogin credentials:")
    print("Username: admin")
    print("Password: admin123")
    print("\nAccess the application at: http://localhost:8000")
    
    # Print some QR code URLs for testing
    print("\nSample QR Code URLs for testing:")
    for event in Event.objects.filter(is_active=True)[:3]:
        print(f"{event.name}: http://localhost:8000/scan/{event.qr_code}/")

if __name__ == '__main__':
    create_sample_data()

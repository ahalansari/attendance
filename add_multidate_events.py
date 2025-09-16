#!/usr/bin/env python
"""
Script to add sample multi-date events for testing
"""

import os
import django
from datetime import datetime, timedelta

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'attendance_system.settings')
django.setup()

from django.contrib.auth.models import User
from events.models import Event, EventSession

def create_multidate_events():
    """Create sample multi-date events"""
    
    # Get admin user
    admin_user = User.objects.get(username='admin')
    
    # Create a multi-day course event
    course_event = Event.objects.create(
        name='Python Programming Course',
        description='5-day intensive Python programming course for beginners',
        event_type='span',
        date=datetime.now().date() + timedelta(days=1),
        end_date=datetime.now().date() + timedelta(days=5),
        start_time='09:00',
        end_time='17:00',
        location='Computer Lab A',
        created_by=admin_user
    )
    
    # Generate sessions for the course
    course_event.generate_sessions()
    print(f"Created course event: {course_event.name}")
    print(f"Generated {course_event.total_sessions} sessions")
    
    # Create a recurring seminar event
    seminar_event = Event.objects.create(
        name='Weekly Leadership Seminar',
        description='Weekly seminar series on leadership and management',
        event_type='recurring',
        date=datetime.now().date() + timedelta(days=7),
        end_date=datetime.now().date() + timedelta(days=28),  # 4 weeks
        start_time='14:00',
        end_time='16:00',
        location='Conference Room B',
        created_by=admin_user
    )
    
    # Generate sessions for the seminar (every 7 days)
    current_date = seminar_event.date
    session_num = 1
    while current_date <= seminar_event.end_date:
        EventSession.objects.create(
            event=seminar_event,
            session_date=current_date,
            session_number=session_num,
            start_time=seminar_event.start_time,
            end_time=seminar_event.end_time,
            location=seminar_event.location,
            notes=f'Week {session_num} - Leadership fundamentals'
        )
        current_date += timedelta(days=7)
        session_num += 1
    
    print(f"Created seminar event: {seminar_event.name}")
    print(f"Generated {seminar_event.total_sessions} sessions")
    
    # Create a student attendance tracking event (month-long)
    student_event = Event.objects.create(
        name='Student Daily Attendance - October 2024',
        description='Daily attendance tracking for students',
        event_type='span',
        date=datetime.now().date() + timedelta(days=10),
        end_date=datetime.now().date() + timedelta(days=40),  # 30 days
        start_time='08:00',
        end_time='16:00',
        location='Classroom 101',
        created_by=admin_user
    )
    
    # Generate sessions (only weekdays)
    current_date = student_event.date
    session_num = 1
    while current_date <= student_event.end_date:
        # Only create sessions for weekdays (Monday = 0, Sunday = 6)
        if current_date.weekday() < 5:  # Monday to Friday
            EventSession.objects.create(
                event=student_event,
                session_date=current_date,
                session_number=session_num,
                start_time=student_event.start_time,
                end_time=student_event.end_time,
                location=student_event.location,
                notes=f'Day {session_num} - Regular class day'
            )
            session_num += 1
        current_date += timedelta(days=1)
    
    print(f"Created student event: {student_event.name}")
    print(f"Generated {student_event.total_sessions} sessions (weekdays only)")
    
    print("\nSample QR Code URLs for session testing:")
    for event in [course_event, seminar_event, student_event]:
        first_session = EventSession.objects.filter(event=event).first()
        if first_session:
            print(f"{event.name} (Session 1): http://localhost:8001/scan/session/{first_session.qr_code}/")
    
    print("\nMulti-date events created successfully!")
    print("Login at: http://localhost:8001/login/")
    print("Username: admin")
    print("Password: admin123")

if __name__ == '__main__':
    create_multidate_events()

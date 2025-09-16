# QR Code Attendance System - Technical Specification

## Project Overview

A Django web application for managing event attendance through QR code scanning. The system allows administrators to generate QR codes for events and attendees to scan these codes to record their attendance using a simple 5-digit ID system.

## System Requirements

### Core Features
1. **Admin Authentication & Management**
   - Secure login system for administrators
   - Admin dashboard for event and attendee management
   - QR code generation and printing functionality

2. **Attendee Registration & Management**
   - Simple 5-digit ID system for attendees
   - Admin can register/manage attendee IDs
   - Device footprint capture for additional tracking

3. **QR Code System**
   - Dynamic QR code generation for events
   - Unique codes per event/session
   - Print-friendly QR code format

4. **Attendance Recording**
   - Mobile-friendly scanning interface
   - ID verification system
   - Real-time attendance logging
   - Device footprint capture

5. **Data Export**
   - Excel/CSV export functionality
   - Comprehensive attendance reports
   - Filterable data by date, event, or attendee

## Technical Architecture

### Technology Stack
- **Backend Framework**: Django 4.2+
- **Database**: SQLite (development) / PostgreSQL (production)
- **Frontend**: Django Templates + Bootstrap 5
- **QR Code Generation**: qrcode library
- **Excel Export**: openpyxl
- **Authentication**: Django's built-in auth system
- **Deployment**: Gunicorn + Nginx (production)

### System Architecture
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Admin Panel   │    │  QR Generator   │    │   Attendance    │
│   (Desktop)     │    │    Service      │    │   Scanner       │
│                 │    │                 │    │   (Mobile)      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                    ┌─────────────────┐
                    │  Django Web     │
                    │  Application    │
                    └─────────────────┘
                                 │
                    ┌─────────────────┐
                    │    Database     │
                    │   (SQLite/PG)   │
                    └─────────────────┘
```

## Data Models

### 1. Event Model
```python
class Event(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    location = models.CharField(max_length=300)
    qr_code = models.CharField(max_length=50, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
```

### 2. Attendee Model
```python
class Attendee(models.Model):
    attendee_id = models.CharField(max_length=5, unique=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
```

### 3. Attendance Record Model
```python
class AttendanceRecord(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    attendee = models.ForeignKey(Attendee, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    device_fingerprint = models.TextField()
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField()
    
    class Meta:
        unique_together = ['event', 'attendee']
```

### 4. Device Footprint Model
```python
class DeviceFootprint(models.Model):
    attendance_record = models.OneToOneField(AttendanceRecord, on_delete=models.CASCADE)
    screen_resolution = models.CharField(max_length=20, blank=True)
    timezone = models.CharField(max_length=50, blank=True)
    language = models.CharField(max_length=10, blank=True)
    platform = models.CharField(max_length=50, blank=True)
    browser_fingerprint = models.TextField(blank=True)
```

## Application Structure

### Django Apps
1. **accounts** - User authentication and admin management
2. **events** - Event creation and QR code generation
3. **attendees** - Attendee registration and management
4. **attendance** - Attendance recording and scanning
5. **reports** - Data export and reporting

### URL Structure
```
/admin/                    # Django admin interface
/login/                    # Admin login
/logout/                   # Admin logout
/dashboard/                # Admin dashboard
/events/                   # Event management
/events/create/            # Create new event
/events/<id>/qr/           # Generate/view QR code
/events/<id>/print/        # Print-friendly QR code
/attendees/                # Attendee management
/attendees/create/         # Register new attendee
/attendees/bulk-import/    # Bulk import attendees
/scan/<qr_code>/           # Attendance scanning page
/attendance/records/       # View attendance records
/reports/export/           # Export attendance data
```

## Core Features Implementation

### 1. Admin Authentication
- Django's built-in User model and authentication
- Login required decorators for admin views
- Session management
- Password reset functionality

### 2. QR Code Generation
```python
import qrcode
from django.conf import settings

def generate_qr_code(event):
    qr_data = f"{settings.SITE_URL}/scan/{event.qr_code}/"
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(qr_data)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white")
```

### 3. Attendance Scanning
- Mobile-responsive scanning interface
- JavaScript for device fingerprinting
- AJAX submission for seamless experience
- Real-time validation of attendee IDs

### 4. Device Fingerprinting
```javascript
function getDeviceFingerprint() {
    return {
        screen: `${screen.width}x${screen.height}`,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        language: navigator.language,
        platform: navigator.platform,
        userAgent: navigator.userAgent
    };
}
```

### 5. Data Export
- Excel export using openpyxl
- CSV export option
- Filtered exports by date range, event, or attendee
- Scheduled report generation

## Security Considerations

### 1. Authentication & Authorization
- Strong password requirements
- Session timeout configuration
- CSRF protection (Django default)
- Admin-only access to management features

### 2. QR Code Security
- Unique, unpredictable QR codes
- Time-based QR code expiration
- Rate limiting for scanning attempts

### 3. Data Protection
- Input validation and sanitization
- SQL injection prevention (Django ORM)
- XSS protection (Django templates)
- HTTPS enforcement in production

### 4. Privacy
- Anonymized device fingerprinting
- Data retention policies
- GDPR compliance considerations

## Database Schema

### Tables Overview
1. **auth_user** - Django's built-in user table
2. **events_event** - Event information and QR codes
3. **attendees_attendee** - Registered attendees
4. **attendance_attendancerecord** - Attendance logs
5. **attendance_devicefootprint** - Device tracking data

### Indexes
- attendee_id (unique)
- event.qr_code (unique)
- event.date, event.is_active
- attendance_record.timestamp
- attendance_record.event_id, attendee_id (composite unique)

## API Endpoints (Internal)

### Admin APIs
- `POST /api/events/` - Create event
- `GET /api/events/<id>/attendees/` - Get event attendees
- `POST /api/attendees/` - Register attendee
- `GET /api/reports/export/` - Export data

### Scanning APIs
- `GET /api/scan/<qr_code>/` - Validate QR code
- `POST /api/attendance/` - Record attendance
- `POST /api/validate-id/` - Validate attendee ID

## Frontend Components

### 1. Admin Dashboard
- Event management cards
- Quick stats (total events, attendees, today's attendance)
- Recent activity feed
- Export quick actions

### 2. QR Code Generator
- Event details form
- Live QR code preview
- Print layout with event details
- Bulk QR generation for multiple events

### 3. Attendee Scanner (Mobile)
- Clean, mobile-first interface
- Large input field for 5-digit ID
- Success/error feedback
- Device information capture

### 4. Reports & Analytics
- Attendance charts and graphs
- Filterable data tables
- Export options (Excel, CSV, PDF)
- Real-time attendance tracking

## Development Setup

### 1. Prerequisites
- Python 3.8+
- pip package manager
- Virtual environment tool

### 2. Dependencies
```
Django==4.2.*
qrcode[pil]==7.*
openpyxl==3.*
Pillow==10.*
python-decouple==3.*
whitenoise==6.*
gunicorn==21.*
```

### 3. Environment Variables
```
SECRET_KEY=your-secret-key
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=sqlite:///db.sqlite3
SITE_URL=http://localhost:8000
```

## Deployment Architecture

### 1. Production Setup
- **Web Server**: Nginx
- **Application Server**: Gunicorn
- **Database**: PostgreSQL
- **Static Files**: Nginx + WhiteNoise
- **SSL**: Let's Encrypt

### 2. Infrastructure
```
Internet → Nginx → Gunicorn → Django → PostgreSQL
                ↓
            Static Files
```

### 3. Performance Considerations
- Database connection pooling
- Static file caching
- Gzip compression
- CDN for static assets (optional)

## Testing Strategy

### 1. Unit Tests
- Model validation tests
- QR code generation tests
- Authentication tests
- Data export functionality

### 2. Integration Tests
- End-to-end attendance flow
- Admin workflow testing
- Mobile scanning interface
- Report generation

### 3. Performance Tests
- Concurrent scanning load tests
- Database performance under load
- Export functionality with large datasets

## Monitoring & Logging

### 1. Application Logging
- User authentication logs
- Attendance scanning logs
- Error tracking and reporting
- Performance metrics

### 2. System Monitoring
- Server resource usage
- Database performance
- Response time monitoring
- Uptime monitoring

## Maintenance & Support

### 1. Regular Maintenance
- Database backups
- Log rotation
- Security updates
- Performance optimization

### 2. Data Management
- Attendance data archiving
- User session cleanup
- QR code expiration management
- Export data retention

## Future Enhancements

### Phase 2 Features
- Mobile app for scanning
- Real-time attendance dashboard
- Email notifications
- Advanced analytics and reporting

### Phase 3 Features
- Multi-tenant support
- API for third-party integrations
- Advanced device fingerprinting
- Facial recognition integration

## Success Metrics

### 1. Performance Metrics
- Page load times < 2 seconds
- QR code generation < 1 second
- Attendance recording < 3 seconds
- 99.9% uptime

### 2. User Experience Metrics
- Successful scan rate > 95%
- Admin task completion rate > 90%
- Mobile usability score > 85%
- User satisfaction > 4.5/5

## Project Timeline

### Week 1-2: Core Development
- Django project setup
- User authentication system
- Basic event and attendee models
- QR code generation

### Week 3-4: Attendance System
- Scanning interface development
- Attendance recording logic
- Device fingerprinting
- Mobile optimization

### Week 5-6: Admin Features
- Admin dashboard
- Event management interface
- Attendee management
- Basic reporting

### Week 7-8: Export & Polish
- Excel/CSV export functionality
- UI/UX improvements
- Testing and bug fixes
- Documentation

### Week 9-10: Deployment & Testing
- Production setup
- Performance testing
- Security audit
- User acceptance testing

---

## Conclusion

This technical specification outlines a comprehensive Django-based QR code attendance system that meets all specified requirements. The system provides a secure, scalable, and user-friendly solution for managing event attendance with robust reporting capabilities and mobile-optimized scanning interface.

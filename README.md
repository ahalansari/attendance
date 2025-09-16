# QR Code Attendance System

A professional Django web application for managing event attendance through QR code scanning. The system allows administrators to generate QR codes for events and attendees to scan these codes to record their attendance using a simple 5-digit ID system.

## Features

- **Admin Authentication & Management**: Secure login system with admin dashboard
- **Event Management**: Create, edit, and manage events with automatic QR code generation
- **Attendee Registration**: Simple 5-digit ID system for attendees with bulk import capability
- **QR Code System**: Dynamic QR code generation with print-friendly formats
- **Mobile-Friendly Scanning**: Responsive attendance recording interface
- **Device Fingerprinting**: Enhanced security with device tracking
- **Data Export**: Excel and CSV export functionality with filtering options
- **Real-time Dashboard**: Live attendance tracking and analytics

## Technology Stack

- **Backend**: Django 4.2+
- **Database**: SQLite (development) / PostgreSQL (production ready)
- **Frontend**: Bootstrap 5 with responsive design
- **QR Code Generation**: qrcode library
- **Excel Export**: openpyxl
- **Authentication**: Django's built-in auth system

## Quick Start

### 1. Setup Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Environment Configuration

Create a `.env` file in the project root:

```
SECRET_KEY=your-super-secret-key-change-in-production
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=sqlite:///db.sqlite3
SITE_URL=http://localhost:8000
```

### 4. Database Setup

```bash
python manage.py migrate
python manage.py createsuperuser
```

### 5. Run Development Server

```bash
python manage.py runserver
```

Visit `http://localhost:8000` to access the application.

## Default Admin Credentials

- **Username**: admin
- **Password**: admin123

## Usage

### Admin Dashboard
1. Login at `/login/` with admin credentials
2. Access the dashboard to view stats and recent activity
3. Manage events, attendees, and view reports

### Creating Events
1. Navigate to Events → Create Event
2. Fill in event details (name, date, time, location)
3. QR code is automatically generated
4. Print or display QR code for attendees

### Attendee Registration
1. Navigate to Attendees → Create Attendee
2. Register attendees manually or use bulk import
3. Each attendee gets a unique 5-digit ID

### Recording Attendance
1. Attendees scan the QR code with their mobile device
2. Enter their 5-digit ID on the scanning page
3. Attendance is recorded with timestamp and device info

### Generating Reports
1. Navigate to Reports section
2. Filter by date range or specific events
3. Export data as Excel or CSV files

## API Endpoints

### Admin APIs
- `POST /api/events/` - Create event
- `GET /api/events/<id>/attendees/` - Get event attendees
- `POST /api/attendees/` - Register attendee

### Scanning APIs
- `GET /scan/<qr_code>/` - Attendance scanning page
- `POST /attendance/api/record/` - Record attendance
- `POST /attendance/api/validate-id/` - Validate attendee ID

## Project Structure

```
attendance_system/
├── accounts/           # User authentication and dashboard
├── events/             # Event management and QR generation
├── attendees/          # Attendee registration and management
├── attendance/         # Attendance recording and scanning
├── reports/            # Data export and reporting
├── templates/          # HTML templates
├── static/             # CSS, JavaScript, images
├── media/              # User uploaded files
└── attendance_system/  # Main project settings
```

## Models

### Event
- Name, description, date, time, location
- Auto-generated unique QR code
- Active/inactive status
- Creator tracking

### Attendee
- Auto-generated 5-digit ID
- Personal information (name, email, phone)
- Active/inactive status
- Creator tracking

### AttendanceRecord
- Event and attendee relationship
- Timestamp, IP address, user agent
- Device fingerprinting data
- Unique constraint per event-attendee pair

## Security Features

- CSRF protection
- SQL injection prevention
- XSS protection
- Session management
- Device fingerprinting
- Input validation and sanitization

## Production Deployment

### Environment Variables
```
SECRET_KEY=your-production-secret-key
DEBUG=False
ALLOWED_HOSTS=yourdomain.com
DATABASE_URL=postgresql://user:pass@localhost/dbname
SITE_URL=https://yourdomain.com
```

### Static Files
```bash
python manage.py collectstatic
```

### WSGI Configuration
The application is ready for deployment with Gunicorn + Nginx.

## Database Schema

- **auth_user**: Django's built-in user table
- **events_event**: Event information and QR codes
- **attendees_attendee**: Registered attendees
- **attendance_attendancerecord**: Attendance logs
- **attendance_devicefootprint**: Device tracking data

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License.

## Support

For support and questions, please create an issue in the repository.

---

**QR Code Attendance System** - Professional event attendance tracking made simple.

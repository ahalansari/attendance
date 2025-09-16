# Unraid Docker Deployment Guide

This guide will help you deploy the Django Attendance System on Unraid using Docker Compose.

## Prerequisites

1. **Unraid Server** with Docker service enabled
2. **Docker Compose Manager Plugin** (Community Applications)
3. **Sufficient storage space** (~2GB for initial setup)

## Installation Steps

### Step 1: Install Docker Compose Manager Plugin

1. Go to **Apps** tab in Unraid
2. Search for "**Docker Compose Manager**"
3. Install the plugin by **dcflachs**

### Step 2: Prepare Application Directory

1. Create the application directory structure:
   ```bash
   mkdir -p /mnt/user/appdata/attendance/{app,postgres,redis,static,media}
   ```

2. Copy your application files to `/mnt/user/appdata/attendance/app/`
   - You can use the Unraid file manager or SSH to copy files
   - Ensure all Django files are in this directory

### Step 3: Configure Environment Variables

1. Copy the environment file:
   ```bash
   cp /mnt/user/appdata/attendance/app/unraid.env /mnt/user/appdata/attendance/.env
   ```

2. Edit `/mnt/user/appdata/attendance/.env` with your settings:
   ```bash
   nano /mnt/user/appdata/attendance/.env
   ```

   **Important settings to change:**
   - `SECRET_KEY`: Generate a secure random key
   - `POSTGRES_PASSWORD`: Set a strong database password
   - `UNRAID_IP`: Your Unraid server's IP address
   - `WEB_PORT`: Port for web access (default: 8000)

### Step 4: Copy Database Initialization File

```bash
cp /mnt/user/appdata/attendance/app/init-db.sql /mnt/user/appdata/attendance/
```

### Step 5: Deploy with Docker Compose Manager

1. Open **Docker Compose Manager** from Unraid settings
2. Click "**Add New Stack**"
3. Set **Stack Name**: `attendance-system`
4. Set **Compose File Path**: `/mnt/user/appdata/attendance/unraid-docker-compose.yml`
5. Copy the contents of `unraid-docker-compose.yml` into the editor
6. Click "**Create Stack**"

### Step 6: Start the Stack

1. In Docker Compose Manager, find your "attendance-system" stack
2. Click "**Start**" or "**Up**"
3. Monitor the logs for any errors

## Accessing the Application

- **Web Interface**: `http://YOUR_UNRAID_IP:8000`
- **Admin Panel**: `http://YOUR_UNRAID_IP:8000/admin/`

## Default Admin Account

After first deployment, create a superuser:

```bash
# Access the web container
docker exec -it attendance_web python manage.py createsuperuser
```

## Troubleshooting

### Container Won't Start

1. **Check logs**:
   ```bash
   docker logs attendance_web
   docker logs attendance_db
   ```

2. **Common issues**:
   - Database not ready: Wait for PostgreSQL to fully start
   - Permission issues: Check file ownership in appdata directory
   - Port conflicts: Change WEB_PORT in .env file

### Database Issues

1. **Reset database** (⚠️ **Data loss**):
   ```bash
   docker-compose down -v
   rm -rf /mnt/user/appdata/attendance/postgres/*
   docker-compose up -d
   ```

2. **Manual database access**:
   ```bash
   docker exec -it attendance_db psql -U attendance_user -d attendance_db
   ```

### File Permissions

If you encounter permission issues:
```bash
sudo chown -R 999:999 /mnt/user/appdata/attendance/postgres
sudo chown -R 1000:1000 /mnt/user/appdata/attendance/static
sudo chown -R 1000:1000 /mnt/user/appdata/attendance/media
```

## Updating the Application

1. **Stop the stack** in Docker Compose Manager
2. **Update application files** in `/mnt/user/appdata/attendance/app/`
3. **Rebuild and start**:
   ```bash
   cd /mnt/user/appdata/attendance
   docker-compose build --no-cache attendance_web
   ```
4. **Start the stack** again

## Backup Strategy

### Database Backup
```bash
docker exec attendance_db pg_dump -U attendance_user attendance_db > backup_$(date +%Y%m%d).sql
```

### Full Backup
- Backup entire `/mnt/user/appdata/attendance/` directory
- This includes database, uploaded files, and configuration

## Performance Tuning

### For Production Use

1. **Increase workers** in docker-compose.yml:
   ```yaml
   command: >
     sh -c "python manage.py collectstatic --noinput &&
            python manage.py migrate &&
            gunicorn attendance_system.wsgi:application --bind 0.0.0.0:8000 --workers 5 --access-logfile - --error-logfile -"
   ```

2. **Add resource limits**:
   ```yaml
   deploy:
     resources:
       limits:
         memory: 1G
         cpus: '1.0'
   ```

## Security Considerations

### Local Network Deployment
- The configuration is optimized for local network use
- SSL/HTTPS is disabled for simplicity
- Change default passwords immediately

### Internet Exposure
If exposing to internet, consider:
- Enable SSL/HTTPS
- Use a reverse proxy (nginx/traefik)
- Enable additional security headers
- Use strong passwords and keys

## Advanced Configuration

### Using Pre-built Docker Image

Instead of building locally, you can push to Docker Hub and use:

```yaml
attendance_web:
  image: yourusername/attendance:latest
  # Remove build section
```

### Custom Network Configuration

For integration with other services:

```yaml
networks:
  attendance_network:
    external: true
    name: custom_network
```

## Support

- Check Docker logs for errors
- Verify environment variables
- Ensure all required files are in place
- Test database connectivity

## File Structure

```
/mnt/user/appdata/attendance/
├── app/                          # Django application files
│   ├── manage.py
│   ├── requirements.txt
│   ├── attendance_system/
│   ├── accounts/
│   ├── attendance/
│   ├── events/
│   └── ...
├── .env                          # Environment variables
├── unraid-docker-compose.yml     # Docker Compose file
├── init-db.sql                   # Database initialization
├── postgres/                     # PostgreSQL data
├── redis/                        # Redis data
├── static/                       # Static files
└── media/                        # Uploaded files
```

This deployment provides a robust, scalable attendance system running on your Unraid server with proper data persistence and easy management through the Docker Compose Manager interface.

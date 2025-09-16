# QR Code Attendance System - Production Deployment Guide

This guide covers deploying the QR Code Attendance System using Docker Compose with PostgreSQL in a production environment.

## 🏗️ **Architecture Overview**

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│     Nginx       │    │   Django Web    │    │   PostgreSQL    │
│  (Reverse Proxy)│◄──►│   Application   │◄──►│    Database     │
│   Load Balancer │    │      + GPS      │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
    Port 80/443              Port 8000               Port 5432
                                │
                                ▼
                        ┌─────────────────┐
                        │      Redis      │
                        │     (Cache)     │
                        └─────────────────┘
```

## 📋 **Services Included**

- **nginx**: Reverse proxy with SSL termination, static file serving, and rate limiting
- **web**: Django application with GPS location tracking
- **db**: PostgreSQL 15 database with optimized settings
- **redis**: Redis cache for sessions and performance

## 🚀 **Quick Start**

### 1. **Prerequisites**

```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

### 2. **Environment Configuration**

```bash
# Copy environment template
cp env.example .env

# Edit environment variables
nano .env
```

**Required Environment Variables:**
```env
SECRET_KEY=your-super-secret-key-change-this-in-production
POSTGRES_PASSWORD=your-strong-password-here
DOMAIN_NAME=attendance.yourdomain.com
ALLOWED_HOSTS=localhost,127.0.0.1,attendance.yourdomain.com
CSRF_TRUSTED_ORIGINS=https://attendance.yourdomain.com
```

### 3. **Deploy**

```bash
# Make deployment script executable
chmod +x deploy.sh

# Deploy for production
./deploy.sh prod

# Or deploy for development
./deploy.sh
```

## 🔧 **Manual Deployment**

### **Production Deployment**

```bash
# Pull and build
docker-compose pull
docker-compose build

# Start production services
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Run migrations
docker-compose exec web python manage.py migrate

# Collect static files
docker-compose exec web python manage.py collectstatic --noinput

# Create superuser
docker-compose exec web python manage.py createsuperuser
```

### **Development Deployment**

```bash
# Start development services (includes auto-reload)
docker-compose up -d

# The override file automatically enables debug mode and volume mounting
```

## 🔐 **SSL/TLS Configuration**

### **Self-Signed Certificates (Development)**

The deployment script automatically generates self-signed certificates:

```bash
openssl req -x509 -newkey rsa:4096 -keyout ssl_certs/key.pem -out ssl_certs/cert.pem -days 365 -nodes
```

### **Production Certificates**

Replace self-signed certificates with real ones:

```bash
# Using Let's Encrypt (recommended)
certbot certonly --standalone -d attendance.yourdomain.com

# Copy certificates
cp /etc/letsencrypt/live/attendance.yourdomain.com/fullchain.pem ssl_certs/cert.pem
cp /etc/letsencrypt/live/attendance.yourdomain.com/privkey.pem ssl_certs/key.pem

# Restart nginx
docker-compose restart nginx
```

## 📊 **Database Management**

### **Backup Database**

```bash
# Create backup
docker-compose exec db pg_dump -U attendance_user attendance_db > backup_$(date +%Y%m%d_%H%M%S).sql

# Automated daily backups
echo "0 2 * * * cd /path/to/attendance && docker-compose exec db pg_dump -U attendance_user attendance_db > backups/backup_\$(date +\%Y\%m\%d_\%H\%M\%S).sql" | crontab -
```

### **Restore Database**

```bash
# Restore from backup
docker-compose exec -T db psql -U attendance_user attendance_db < backup.sql
```

### **Database Maintenance**

```bash
# Connect to database
docker-compose exec db psql -U attendance_user attendance_db

# View database size
docker-compose exec db psql -U attendance_user attendance_db -c "SELECT pg_size_pretty(pg_database_size('attendance_db'));"

# Vacuum and analyze
docker-compose exec db psql -U attendance_user attendance_db -c "VACUUM ANALYZE;"
```

## 📈 **Monitoring and Logs**

### **View Logs**

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f web
docker-compose logs -f db
docker-compose logs -f nginx
docker-compose logs -f redis
```

### **Health Checks**

```bash
# Application health
curl https://localhost/health/

# Service status
docker-compose ps

# Resource usage
docker stats
```

### **Performance Monitoring**

```bash
# Database connections
docker-compose exec db psql -U attendance_user attendance_db -c "SELECT count(*) FROM pg_stat_activity;"

# Cache statistics
docker-compose exec redis redis-cli info stats

# Nginx access logs
docker-compose logs nginx | grep "GET\|POST"
```

## 🔄 **Maintenance Commands**

### **Update Application**

```bash
# Pull latest changes
git pull origin main

# Rebuild and restart
docker-compose build web
docker-compose up -d web

# Run migrations if needed
docker-compose exec web python manage.py migrate
```

### **Scale Services**

```bash
# Scale web workers
docker-compose up -d --scale web=3

# Update nginx upstream (manual configuration needed)
```

### **Backup Management**

```bash
# Cleanup old backups (keep last 30 days)
find backups/ -name "backup_*.sql" -mtime +30 -delete

# Compress backups
gzip backups/backup_*.sql
```

## 🚨 **Troubleshooting**

### **Common Issues**

1. **Port already in use**
   ```bash
   sudo netstat -tulpn | grep :80
   sudo systemctl stop apache2  # if Apache is running
   ```

2. **Permission denied**
   ```bash
   sudo chown -R $USER:$USER .
   chmod +x deploy.sh
   ```

3. **Database connection failed**
   ```bash
   docker-compose logs db
   docker-compose exec db pg_isready -U attendance_user
   ```

4. **SSL certificate issues**
   ```bash
   # Check certificate
   openssl x509 -in ssl_certs/cert.pem -text -noout
   
   # Regenerate if needed
   rm ssl_certs/*
   ./deploy.sh prod
   ```

### **Emergency Recovery**

```bash
# Stop all services
docker-compose down

# Remove all containers (DESTRUCTIVE)
docker-compose down -v

# Restore from backup
./deploy.sh prod
docker-compose exec -T db psql -U attendance_user attendance_db < latest_backup.sql
```

## 🏭 **Production Optimizations**

### **Resource Limits**

Add to `docker-compose.prod.yml`:

```yaml
services:
  web:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 2G
        reservations:
          cpus: '1.0'
          memory: 1G
```

### **Log Rotation**

```bash
# Configure log rotation
cat > /etc/logrotate.d/docker-compose << EOF
/var/lib/docker/containers/*/*.log {
  rotate 30
  daily
  compress
  size=1M
  missingok
  delaycompress
  copytruncate
}
EOF
```

## 📱 **GPS Location Features**

The system includes GPS location tracking for attendance verification:

- **Real-time location capture** during QR code scanning
- **Privacy-compliant** with clear user notices
- **Fallback support** when GPS is unavailable
- **Admin visibility** of location data for verification

## 🌐 **Domain and DNS Setup**

### **DNS Configuration**

```bash
# A Record
attendance.yourdomain.com -> YOUR_SERVER_IP

# Optional: Subdomain
attendance -> YOUR_SERVER_IP
```

### **Firewall Configuration**

```bash
# Ubuntu/Debian
sudo ufw allow 80
sudo ufw allow 443
sudo ufw allow 22  # SSH

# CentOS/RHEL
sudo firewall-cmd --permanent --add-port=80/tcp
sudo firewall-cmd --permanent --add-port=443/tcp
sudo firewall-cmd --reload
```

---

## 📞 **Support**

For issues and questions:

1. Check logs: `docker-compose logs -f`
2. Verify service health: `curl https://localhost/health/`
3. Review this documentation
4. Check Docker and system resources

## 🔄 **Updates**

To update the system:

1. Pull latest code: `git pull`
2. Rebuild: `docker-compose build`
3. Deploy: `./deploy.sh prod`
4. Run migrations: `docker-compose exec web python manage.py migrate`

The system is designed for zero-downtime updates with proper orchestration.

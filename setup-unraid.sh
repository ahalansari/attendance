#!/bin/bash

# Unraid Docker Deployment Setup Script
# Run this script on your Unraid server to quickly set up the attendance system

set -e

# Configuration
APPDATA_DIR="/mnt/user/appdata/attendance"
APP_DIR="$APPDATA_DIR/app"
REPO_URL="https://github.com/ahalansari/attendance.git"

echo "🚀 Setting up Django Attendance System on Unraid..."

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   echo "⚠️  Running as root. This is fine for Unraid setup."
fi

# Create directory structure
echo "📁 Creating directory structure..."
mkdir -p "$APPDATA_DIR"/{app,postgres,redis,static,media}

# Clone or update repository
if [ -d "$APP_DIR/.git" ]; then
    echo "📦 Updating existing application..."
    cd "$APP_DIR"
    git pull
else
    echo "📦 Cloning application repository..."
    git clone "$REPO_URL" "$APP_DIR"
fi

# Copy configuration files
echo "⚙️  Setting up configuration..."
cd "$APP_DIR"

# Copy environment file
if [ ! -f "$APPDATA_DIR/.env" ]; then
    cp unraid.env "$APPDATA_DIR/.env"
    echo "✅ Environment file created at $APPDATA_DIR/.env"
    echo "⚠️  Please edit $APPDATA_DIR/.env with your settings!"
else
    echo "ℹ️  Environment file already exists, skipping..."
fi

# Copy docker-compose file
cp unraid-docker-compose.yml "$APPDATA_DIR/"
echo "✅ Docker Compose file copied"

# Copy database initialization
cp init-db.sql "$APPDATA_DIR/"
echo "✅ Database initialization file copied"

# Set permissions
echo "🔒 Setting permissions..."
chown -R 999:999 "$APPDATA_DIR/postgres" 2>/dev/null || true
chown -R 1000:1000 "$APPDATA_DIR/static" "$APPDATA_DIR/media" 2>/dev/null || true

# Generate a random secret key if not exists
if ! grep -q "your-super-secret-key-change-this" "$APPDATA_DIR/.env" 2>/dev/null; then
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(50))" 2>/dev/null || openssl rand -base64 32)
    sed -i "s/your-super-secret-key-change-this-in-production-make-it-long-and-random/$SECRET_KEY/g" "$APPDATA_DIR/.env"
    echo "✅ Generated random secret key"
fi

# Get Unraid IP
UNRAID_IP=$(ip route get 1.1.1.1 | awk '{print $7}' | head -n1)
if [ ! -z "$UNRAID_IP" ]; then
    sed -i "s/192.168.1.100/$UNRAID_IP/g" "$APPDATA_DIR/.env"
    echo "✅ Set Unraid IP to $UNRAID_IP"
fi

echo ""
echo "🎉 Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit $APPDATA_DIR/.env with your preferences"
echo "2. Install 'Docker Compose Manager' plugin from Community Applications"
echo "3. In Docker Compose Manager, create a new stack with:"
echo "   - Stack Name: attendance-system"
echo "   - Compose File: $APPDATA_DIR/unraid-docker-compose.yml"
echo "4. Start the stack"
echo "5. Access your application at: http://$UNRAID_IP:8000"
echo ""
echo "📚 For detailed instructions, see: $APP_DIR/UNRAID_DEPLOYMENT.md"
echo ""
echo "⚠️  Remember to:"
echo "   - Change the POSTGRES_PASSWORD in .env"
echo "   - Create a superuser: docker exec -it attendance_web python manage.py createsuperuser"
echo ""

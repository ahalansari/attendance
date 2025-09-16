#!/bin/bash

# QR Code Attendance System - Production Deployment Script
# This script helps deploy the application using Docker Compose

set -e  # Exit on any error

echo "🚀 QR Code Attendance System - Production Deployment"
echo "=================================================="

# Check if Docker and Docker Compose are installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Check if .env file exists
if [ ! -f .env ]; then
    echo "❌ .env file not found. Please create .env file from env.example"
    echo "   cp env.example .env"
    echo "   Then edit .env with your production values"
    exit 1
fi

# Create necessary directories
echo "📁 Creating necessary directories..."
mkdir -p logs ssl_certs backups

# Note: SSL/TLS is handled by Cloudflare Tunnel
echo "🔒 SSL/TLS termination handled by Cloudflare Tunnel"

# Pull latest images
echo "📦 Pulling Docker images..."
docker-compose pull

# Build the application
echo "🔧 Building application..."
docker-compose build

# Start services
echo "🎯 Starting services..."
if [ "$1" = "prod" ]; then
    echo "   Using production configuration..."
    docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
else
    echo "   Using development configuration..."
    docker-compose up -d
fi

# Wait for services to be ready
echo "⏳ Waiting for services to start..."
sleep 30

# Check if services are healthy
echo "🏥 Checking service health..."
if docker-compose ps | grep -q "Up"; then
    echo "✅ Services are running"
else
    echo "❌ Some services failed to start"
    docker-compose logs
    exit 1
fi

# Run database migrations
echo "🗄️  Running database migrations..."
docker-compose exec web python manage.py migrate

# Collect static files
echo "📦 Collecting static files..."
docker-compose exec web python manage.py collectstatic --noinput

# Create superuser (optional)
echo "👤 Create superuser? (y/n)"
read -r create_user
if [ "$create_user" = "y" ]; then
    docker-compose exec web python manage.py createsuperuser
fi

# Display final status
echo ""
echo "🎉 Deployment completed successfully!"
echo ""
echo "📋 Service URLs:"
echo "   Application: http://localhost:8000 (Local)"
echo "   Application: https://your-tunnel-domain.com (Cloudflare Tunnel)"
echo "   Admin: https://your-tunnel-domain.com/admin/"
echo "   Health Check: http://localhost:8000/health/"
echo ""
echo "📊 Service Status:"
docker-compose ps
echo ""
echo "📝 To view logs: docker-compose logs -f"
echo "🛑 To stop: docker-compose down"
echo "🔄 To restart: docker-compose restart"
echo ""
echo "🔧 Useful commands:"
echo "   View logs: docker-compose logs -f [service_name]"
echo "   Execute commands: docker-compose exec web python manage.py [command]"
echo "   Database backup: docker-compose exec db pg_dump -U attendance_user attendance_db > backup.sql"
echo "   Database restore: docker-compose exec -T db psql -U attendance_user attendance_db < backup.sql"

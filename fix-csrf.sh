#!/bin/bash

# Quick CSRF Fix Script for attendance.qitcare.co
# Run this script to fix CSRF issues with your deployment

echo "🔧 Fixing CSRF configuration for attendance.qitcare.co..."

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "❌ .env file not found. Creating from template..."
    cp env.production.example .env
    echo "✅ Created .env file from template"
    echo "⚠️  Please edit .env file with your actual SECRET_KEY and POSTGRES_PASSWORD"
    exit 1
fi

# Update ALLOWED_HOSTS if not already set
if ! grep -q "attendance.qitcare.co" .env; then
    echo "📝 Adding attendance.qitcare.co to ALLOWED_HOSTS..."
    sed -i.bak 's/ALLOWED_HOSTS=\(.*\)/ALLOWED_HOSTS=\1,attendance.qitcare.co/' .env
    echo "✅ Updated ALLOWED_HOSTS"
fi

# Update CSRF_TRUSTED_ORIGINS if not already set
if ! grep -q "https://attendance.qitcare.co" .env; then
    echo "📝 Adding https://attendance.qitcare.co to CSRF_TRUSTED_ORIGINS..."
    sed -i.bak 's/CSRF_TRUSTED_ORIGINS=\(.*\)/CSRF_TRUSTED_ORIGINS=\1,https:\/\/attendance.qitcare.co/' .env
    echo "✅ Updated CSRF_TRUSTED_ORIGINS"
fi

# Ensure CSRF_TRUSTED_ORIGINS exists
if ! grep -q "CSRF_TRUSTED_ORIGINS" .env; then
    echo "📝 Adding CSRF_TRUSTED_ORIGINS configuration..."
    echo "CSRF_TRUSTED_ORIGINS=https://attendance.qitcare.co,http://localhost:8000" >> .env
    echo "✅ Added CSRF_TRUSTED_ORIGINS"
fi

# Add USE_CLOUDFLARE if not exists
if ! grep -q "USE_CLOUDFLARE" .env; then
    echo "📝 Adding Cloudflare configuration..."
    echo "USE_CLOUDFLARE=True" >> .env
    echo "✅ Added Cloudflare configuration"
fi

# Add DOMAIN_NAME if not exists
if ! grep -q "DOMAIN_NAME" .env; then
    echo "📝 Adding domain name configuration..."
    echo "DOMAIN_NAME=attendance.qitcare.co" >> .env
    echo "✅ Added domain name configuration"
fi

echo ""
echo "🎉 Configuration updated! Now restart your Docker containers:"
echo ""
echo "  docker-compose down"
echo "  docker-compose up -d"
echo ""
echo "Or if using Docker Compose Manager in Unraid:"
echo "  1. Stop the stack"
echo "  2. Start the stack again"
echo ""
echo "🔍 Your current .env configuration:"
echo "────────────────────────────────────"
grep -E "(ALLOWED_HOSTS|CSRF_TRUSTED_ORIGINS|USE_CLOUDFLARE|DOMAIN_NAME)" .env
echo "────────────────────────────────────"
echo ""
echo "⚠️  Make sure to set a strong SECRET_KEY and POSTGRES_PASSWORD!"

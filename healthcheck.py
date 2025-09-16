#!/usr/bin/env python
"""
Health check script for Docker container
Checks database connectivity, Redis cache, and basic Django functionality
"""

import os
import sys
import django
from django.conf import settings
from django.core.management import execute_from_command_line

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'attendance_system.settings')
django.setup()

from django.db import connections
from django.core.cache import cache
from django.test.utils import get_runner
import requests


def check_database():
    """Check database connectivity"""
    try:
        db_conn = connections['default']
        db_conn.cursor()
        return True, "Database connection OK"
    except Exception as e:
        return False, f"Database connection failed: {str(e)}"


def check_cache():
    """Check Redis cache connectivity"""
    try:
        cache.set('health_check', 'ok', timeout=60)
        result = cache.get('health_check')
        if result == 'ok':
            cache.delete('health_check')
            return True, "Cache connection OK"
        else:
            return False, "Cache test failed"
    except Exception as e:
        return False, f"Cache connection failed: {str(e)}"


def check_application():
    """Check if Django application is responsive"""
    try:
        response = requests.get('http://localhost:8000/health/', timeout=5)
        if response.status_code == 200:
            return True, "Application responsive"
        else:
            return False, f"Application returned status {response.status_code}"
    except Exception as e:
        return False, f"Application check failed: {str(e)}"


def main():
    """Run all health checks"""
    checks = [
        ("Database", check_database),
        ("Cache", check_cache),
        ("Application", check_application),
    ]
    
    all_passed = True
    results = []
    
    for name, check_func in checks:
        try:
            passed, message = check_func()
            results.append(f"{name}: {'✓' if passed else '✗'} {message}")
            if not passed:
                all_passed = False
        except Exception as e:
            results.append(f"{name}: ✗ Exception: {str(e)}")
            all_passed = False
    
    print("\n".join(results))
    
    if all_passed:
        print("\n🎉 All health checks passed!")
        sys.exit(0)
    else:
        print("\n❌ Some health checks failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()

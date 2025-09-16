"""
URL configuration for attendance_system project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import RedirectView


@csrf_exempt
@require_GET
def health_check(request):
    """Health check endpoint for Docker"""
    from django.db import connections
    from django.core.cache import cache
    
    try:
        # Check database
        db_conn = connections['default']
        db_conn.cursor()
        
        # Check cache
        cache.set('health_check', 'ok', timeout=60)
        cache_result = cache.get('health_check')
        
        if cache_result == 'ok':
            cache.delete('health_check')
            return JsonResponse({
                'status': 'healthy',
                'database': 'ok',
                'cache': 'ok'
            })
        else:
            return JsonResponse({
                'status': 'unhealthy',
                'database': 'ok',
                'cache': 'failed'
            }, status=503)
            
    except Exception as e:
        return JsonResponse({
            'status': 'unhealthy',
            'error': str(e)
        }, status=503)


urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health_check, name="health_check"),
    path("", RedirectView.as_view(url="/dashboard/", permanent=False)),
    path("", include("accounts.urls")),
    path("events/", include("events.urls")),
    path("attendees/", include("attendees.urls")),
    path("attendance/", include("attendance.urls")),
    path("reports/", include("reports.urls")),
    path("scan/", include("attendance.urls", namespace="scan")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

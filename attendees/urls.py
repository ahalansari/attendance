from django.urls import path
from . import views

app_name = 'attendees'

urlpatterns = [
    path('', views.AttendeeListView.as_view(), name='list'),
    path('create/', views.AttendeeCreateView.as_view(), name='create'),
    path('<int:pk>/', views.AttendeeDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', views.AttendeeUpdateView.as_view(), name='edit'),
    path('bulk-import/', views.BulkImportView.as_view(), name='bulk_import'),
]

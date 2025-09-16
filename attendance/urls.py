from django.urls import path
from . import views

app_name = 'attendance'

urlpatterns = [
    path('records/', views.AttendanceRecordListView.as_view(), name='records'),
    path('<str:qr_code>/', views.ScanView.as_view(), name='scan'),
    path('checkpoint/<str:checkpoint_code>/', views.CheckpointScanView.as_view(), name='checkpoint_scan'),
    path('api/record-checkpoint/', views.RecordCheckpointAttendanceView.as_view(), name='record_checkpoint'),
    path('api/record-unified/', views.RecordUnifiedAttendanceView.as_view(), name='record_unified'),
    path('api/validate-id/', views.ValidateAttendeeIDView.as_view(), name='validate_id'),
    path('api/checkpoints/<int:event_id>/', views.GetEventCheckpointsView.as_view(), name='get_checkpoints'),
    path('api/checkpoints/session/<int:session_id>/', views.GetSessionCheckpointsView.as_view(), name='get_session_checkpoints'),
]

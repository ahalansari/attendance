from django.urls import path
from . import views

app_name = 'events'

urlpatterns = [
    path('', views.EventListView.as_view(), name='list'),
    path('create/', views.EventCreateView.as_view(), name='create'),
    path('<int:pk>/', views.EventDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', views.EventUpdateView.as_view(), name='edit'),
    path('<int:pk>/qr/', views.EventQRView.as_view(), name='qr'),
    path('<int:pk>/print/', views.EventPrintView.as_view(), name='print'),
    path('<int:pk>/attendees/', views.EventAttendeesView.as_view(), name='attendees'),
    path('<int:pk>/sessions/', views.EventSessionsView.as_view(), name='sessions'),
    path('<int:pk>/sessions/create/', views.CreateSessionView.as_view(), name='create_session'),
    path('<int:pk>/checkpoints/', views.EventCheckpointsView.as_view(), name='checkpoints'),
    path('<int:pk>/checkpoints/create/', views.CreateCheckpointView.as_view(), name='create_checkpoint'),
    path('<int:pk>/checkpoints/quick/', views.QuickSetupCheckpointsView.as_view(), name='quick_checkpoints'),
    path('<int:pk>/checkpoints/batch/', views.BatchGenerateCheckpointsView.as_view(), name='batch_checkpoints'),
    path('sessions/<int:pk>/qr/', views.SessionQRView.as_view(), name='session_qr'),
    path('sessions/<int:pk>/print/', views.SessionPrintView.as_view(), name='session_print'),
    path('sessions/<int:pk>/checkpoints/', views.SessionCheckpointsView.as_view(), name='session_checkpoints'),
    path('sessions/<int:pk>/checkpoints/create/', views.CreateSessionCheckpointView.as_view(), name='create_session_checkpoint'),
    path('checkpoints/<int:pk>/edit/', views.EditCheckpointView.as_view(), name='edit_checkpoint'),
    path('checkpoints/<int:pk>/delete/', views.DeleteCheckpointView.as_view(), name='delete_checkpoint'),
]

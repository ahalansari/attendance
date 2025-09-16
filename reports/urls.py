from django.urls import path
from . import views

app_name = 'reports'

urlpatterns = [
    path('', views.ReportsView.as_view(), name='index'),
    path('export/', views.ExportView.as_view(), name='export'),
    path('export/excel/', views.ExportExcelView.as_view(), name='export_excel'),
    path('export/csv/', views.ExportCSVView.as_view(), name='export_csv'),
]

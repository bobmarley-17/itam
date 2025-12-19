from django.urls import path
from . import views

app_name = 'assets'

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),
    
    # Assets
    path('assets/', views.asset_list, name='asset_list'),
    path('assets/<int:pk>/', views.asset_detail, name='asset_detail'),
    path('assets/<int:pk>/assign/', views.assign_asset, name='assign_asset'),
    path('assets/<int:pk>/unassign/', views.unassign_asset, name='unassign_asset'),
    path('assets/<int:pk>/qrcode/', views.generate_qr_code, name='generate_qr_code'),
    path('assets/<int:pk>/qrcode/download/', views.download_qr_code, name='download_qr_code'),
    path('assets/<int:pk>/label/', views.print_asset_label, name='print_asset_label'),
    path('assets/<int:pk>/pdf/', views.generate_asset_pdf, name='generate_asset_pdf'),
    path('assets/export/', views.export_assets, name='export_assets'),
    path('assets/export/pdf/', views.generate_all_assets_pdf, name='generate_all_assets_pdf'),
    
    # Bulk Operations
    path('bulk/import/', views.bulk_import, name='bulk_import'),
    path('bulk/import/template/', views.download_import_template, name='download_import_template'),
    path('bulk/import/employees/', views.bulk_import_employees, name='bulk_import_employees'),
    path('bulk/labels/', views.bulk_print_labels, name='bulk_print_labels'),
    
    # Employees
    path('employees/', views.employee_list, name='employee_list'),
    path('employees/<int:pk>/', views.employee_detail, name='employee_detail'),
    path('employees/export/', views.export_employees, name='export_employees'),
    
    # Maintenance
    path('maintenance/', views.maintenance_list, name='maintenance_list'),
    
    # History
    path('history/', views.history_list, name='history_list'),
    
    # Reports
    path('reports/', views.reports, name='reports'),
    path('reports/warranty-alerts/', views.send_warranty_alerts, name='send_warranty_alerts'),
    
    # User Management
    path('users/', views.user_list, name='user_list'),
    path('users/create/', views.create_user, name='create_user'),
    path('users/<int:pk>/', views.user_detail, name='user_detail'),
    path('users/<int:pk>/toggle/', views.user_toggle_active, name='user_toggle_active'),
    path('users/<int:pk>/role/', views.user_change_role, name='user_change_role'),
    path('users/setup-roles/', views.setup_roles, name='setup_roles'),
]

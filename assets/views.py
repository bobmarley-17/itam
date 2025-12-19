from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User, Group
from django.contrib import messages
from django.db.models import Count, Sum, Q
from django.utils import timezone
from django.http import HttpResponse, JsonResponse
from django.core.mail import send_mail, EmailMessage
from django.template.loader import render_to_string
from django.conf import settings
from datetime import timedelta
import json
import os
import io

from .models import (
    Asset, Employee, Category, Department, 
    Location, Vendor, AssetHistory, MaintenanceRecord
)


# ============================================
# DASHBOARD
# ============================================

@login_required
def dashboard(request):
    # Get counts
    total_assets = Asset.objects.count()
    available_assets = Asset.objects.filter(status='available').count()
    assigned_assets = Asset.objects.filter(status='assigned').count()
    maintenance_assets = Asset.objects.filter(status='maintenance').count()
    retired_assets = Asset.objects.filter(status='retired').count()
    
    # Get total value
    total_value = Asset.objects.aggregate(total=Sum('purchase_cost'))['total'] or 0
    
    # Total employees
    total_employees = Employee.objects.filter(is_active=True).count()
    
    # Assets by category for chart
    assets_by_category = Category.objects.annotate(
        count=Count('asset')
    ).filter(count__gt=0).order_by('-count')
    
    # Assets by status for chart
    status_data = {
        'available': available_assets,
        'assigned': assigned_assets,
        'maintenance': maintenance_assets,
        'retired': retired_assets,
    }
    
    # Recent assets
    recent_assets = Asset.objects.select_related(
        'category', 'assigned_to', 'location'
    ).order_by('-created_at')[:10]
    
    # Recent activity
    recent_activity = AssetHistory.objects.select_related(
        'asset', 'performed_by'
    ).order_by('-created_at')[:10]
    
    # Upcoming maintenance
    upcoming_maintenance = MaintenanceRecord.objects.filter(
        status__in=['scheduled', 'in_progress'],
        scheduled_date__gte=timezone.now().date()
    ).select_related('asset').order_by('scheduled_date')[:5]
    
    # Warranty expiring soon (next 30 days)
    thirty_days = timezone.now().date() + timedelta(days=30)
    expiring_warranty = Asset.objects.filter(
        warranty_expiry__lte=thirty_days,
        warranty_expiry__gte=timezone.now().date()
    ).order_by('warranty_expiry')[:5]
    
    # Chart data
    category_labels = [cat.name for cat in assets_by_category]
    category_counts = [cat.count for cat in assets_by_category]
    
    # Status chart data
    status_labels = ['Available', 'Assigned', 'Maintenance', 'Retired']
    status_counts = [available_assets, assigned_assets, maintenance_assets, retired_assets]
    
    # Monthly asset additions (last 6 months)
    from django.db.models.functions import TruncMonth
    monthly_data = Asset.objects.filter(
        created_at__gte=timezone.now() - timedelta(days=180)
    ).annotate(
        month=TruncMonth('created_at')
    ).values('month').annotate(count=Count('id')).order_by('month')
    
    monthly_labels = [item['month'].strftime('%b %Y') for item in monthly_data]
    monthly_counts = [item['count'] for item in monthly_data]
    
    context = {
        'total_assets': total_assets,
        'available_assets': available_assets,
        'assigned_assets': assigned_assets,
        'maintenance_assets': maintenance_assets,
        'retired_assets': retired_assets,
        'total_value': total_value,
        'total_employees': total_employees,
        'assets_by_category': assets_by_category,
        'status_data': status_data,
        'recent_assets': recent_assets,
        'recent_activity': recent_activity,
        'upcoming_maintenance': upcoming_maintenance,
        'expiring_warranty': expiring_warranty,
        # Chart data as JSON
        'category_labels': json.dumps(category_labels),
        'category_counts': json.dumps(category_counts),
        'status_labels': json.dumps(status_labels),
        'status_counts': json.dumps(status_counts),
        'monthly_labels': json.dumps(monthly_labels),
        'monthly_counts': json.dumps(monthly_counts),
    }
    return render(request, 'assets/dashboard.html', context)


# ============================================
# ASSETS
# ============================================

@login_required
def asset_list(request):
    assets = Asset.objects.select_related('category', 'assigned_to', 'location').all()
    
    # Search
    search = request.GET.get('search', '')
    if search:
        assets = assets.filter(
            Q(asset_tag__icontains=search) |
            Q(name__icontains=search) |
            Q(serial_number__icontains=search) |
            Q(manufacturer__icontains=search) |
            Q(model__icontains=search)
        )
    
    # Filter by status
    status = request.GET.get('status', '')
    if status:
        assets = assets.filter(status=status)
    
    # Filter by category
    category = request.GET.get('category', '')
    if category:
        assets = assets.filter(category_id=category)
    
    # Filter by location
    location = request.GET.get('location', '')
    if location:
        assets = assets.filter(location_id=location)
    
    categories = Category.objects.all()
    locations = Location.objects.all()
    
    context = {
        'assets': assets,
        'categories': categories,
        'locations': locations,
        'search': search,
        'status': status,
        'selected_category': category,
        'selected_location': location,
        'total_count': assets.count(),
    }
    return render(request, 'assets/asset_list.html', context)


@login_required
def asset_detail(request, pk):
    asset = get_object_or_404(Asset, pk=pk)
    history = asset.history.all()[:20]
    maintenance = asset.maintenance_records.all()[:10]
    
    # Generate QR code URL
    qr_url = f"/app/assets/{pk}/qrcode/"
    
    context = {
        'asset': asset,
        'history': history,
        'maintenance': maintenance,
        'qr_url': qr_url,
    }
    return render(request, 'assets/asset_detail.html', context)


@login_required
def assign_asset(request, pk):
    asset = get_object_or_404(Asset, pk=pk)
    
    if request.method == 'POST':
        employee_id = request.POST.get('employee_id')
        send_email = request.POST.get('send_email', False)
        
        if employee_id:
            employee = get_object_or_404(Employee, pk=employee_id)
            old_assignee = asset.assigned_to
            
            # Update asset
            asset.assigned_to = employee
            asset.assigned_date = timezone.now().date()
            asset.status = 'assigned'
            asset.save()
            
            # Create history record
            AssetHistory.objects.create(
                asset=asset,
                action='assigned',
                description=f'Asset assigned to {employee.full_name}',
                performed_by=request.user,
                old_value=str(old_assignee) if old_assignee else 'None',
                new_value=employee.full_name
            )
            
            # Send email notification
            if send_email and employee.email:
                try:
                    send_assignment_email(asset, employee, request.user)
                    messages.success(request, f'Asset assigned and email sent to {employee.email}')
                except Exception as e:
                    messages.warning(request, f'Asset assigned but email failed: {str(e)}')
            else:
                messages.success(request, f'Asset {asset.asset_tag} assigned to {employee.full_name}')
            
            return redirect('assets:asset_detail', pk=pk)
    
    employees = Employee.objects.filter(is_active=True).order_by('first_name')
    
    context = {
        'asset': asset,
        'employees': employees,
    }
    return render(request, 'assets/assign_asset.html', context)


@login_required
def unassign_asset(request, pk):
    asset = get_object_or_404(Asset, pk=pk)
    
    if request.method == 'POST':
        old_assignee = asset.assigned_to
        send_email = request.POST.get('send_email', False)
        
        if old_assignee:
            # Update asset
            asset.assigned_to = None
            asset.assigned_date = None
            asset.status = 'available'
            asset.save()
            
            # Create history record
            AssetHistory.objects.create(
                asset=asset,
                action='unassigned',
                description=f'Asset unassigned from {old_assignee.full_name}',
                performed_by=request.user,
                old_value=old_assignee.full_name,
                new_value='None'
            )
            
            # Send email notification
            if send_email and old_assignee.email:
                try:
                    send_unassignment_email(asset, old_assignee, request.user)
                    messages.success(request, f'Asset unassigned and email sent')
                except Exception as e:
                    messages.warning(request, f'Asset unassigned but email failed: {str(e)}')
            else:
                messages.success(request, f'Asset {asset.asset_tag} has been unassigned')
        
        return redirect('assets:asset_detail', pk=pk)
    
    context = {
        'asset': asset,
    }
    return render(request, 'assets/unassign_asset.html', context)


# ============================================
# QR CODE GENERATION
# ============================================

@login_required
def generate_qr_code(request, pk):
    """Generate QR code for an asset"""
    try:
        import qrcode
        from io import BytesIO
    except ImportError:
        messages.error(request, 'qrcode library not installed')
        return redirect('assets:asset_detail', pk=pk)
    
    asset = get_object_or_404(Asset, pk=pk)
    
    # Create QR code data
    qr_data = f"""Asset Tag: {asset.asset_tag}
Name: {asset.name}
Category: {asset.category.name if asset.category else 'N/A'}
Serial: {asset.serial_number or 'N/A'}
Status: {asset.get_status_display()}
URL: {request.build_absolute_uri(f'/app/assets/{pk}/')}"""
    
    # Generate QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(qr_data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Save to response
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    
    response = HttpResponse(buffer.read(), content_type='image/png')
    response['Content-Disposition'] = f'inline; filename="qr_{asset.asset_tag}.png"'
    
    return response


@login_required
def download_qr_code(request, pk):
    """Download QR code as file"""
    try:
        import qrcode
        from io import BytesIO
    except ImportError:
        messages.error(request, 'qrcode library not installed')
        return redirect('assets:asset_detail', pk=pk)
    
    asset = get_object_or_404(Asset, pk=pk)
    
    # QR data with URL
    qr_data = request.build_absolute_uri(f'/app/assets/{pk}/')
    
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(qr_data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    
    response = HttpResponse(buffer.read(), content_type='image/png')
    response['Content-Disposition'] = f'attachment; filename="qr_{asset.asset_tag}.png"'
    
    return response


@login_required
def print_asset_label(request, pk):
    """Print asset label with QR code"""
    asset = get_object_or_404(Asset, pk=pk)
    
    context = {
        'asset': asset,
        'qr_url': f'/app/assets/{pk}/qrcode/',
    }
    return render(request, 'assets/print_label.html', context)


@login_required
def bulk_print_labels(request):
    """Print multiple asset labels"""
    if request.method == 'POST':
        asset_ids = request.POST.getlist('asset_ids')
        assets = Asset.objects.filter(id__in=asset_ids)
        
        context = {
            'assets': assets,
        }
        return render(request, 'assets/bulk_print_labels.html', context)
    
    assets = Asset.objects.all()
    context = {
        'assets': assets,
    }
    return render(request, 'assets/select_labels.html', context)


# ============================================
# BULK IMPORT
# ============================================

@login_required
def bulk_import(request):
    """Bulk import assets from Excel"""
    if request.method == 'POST':
        if 'file' not in request.FILES:
            messages.error(request, 'Please select a file')
            return redirect('assets:bulk_import')
        
        file = request.FILES['file']
        
        if not file.name.endswith(('.xlsx', '.xls')):
            messages.error(request, 'Please upload an Excel file (.xlsx or .xls)')
            return redirect('assets:bulk_import')
        
        try:
            import pandas as pd
            
            # Read Excel file
            df = pd.read_excel(file)
            
            # Required columns
            required_cols = ['asset_tag', 'name']
            for col in required_cols:
                if col not in df.columns:
                    messages.error(request, f'Missing required column: {col}')
                    return redirect('assets:bulk_import')
            
            success_count = 0
            error_count = 0
            errors = []
            
            for index, row in df.iterrows():
                try:
                    # Get or create category
                    category = None
                    if 'category' in df.columns and pd.notna(row.get('category')):
                        category, _ = Category.objects.get_or_create(
                            name=str(row['category']).strip()
                        )
                    
                    # Get or create location
                    location = None
                    if 'location' in df.columns and pd.notna(row.get('location')):
                        location, _ = Location.objects.get_or_create(
                            name=str(row['location']).strip()
                        )
                    
                    # Get or create vendor
                    vendor = None
                    if 'vendor' in df.columns and pd.notna(row.get('vendor')):
                        vendor, _ = Vendor.objects.get_or_create(
                            name=str(row['vendor']).strip()
                        )
                    
                    # Create asset
                    asset, created = Asset.objects.update_or_create(
                        asset_tag=str(row['asset_tag']).strip(),
                        defaults={
                            'name': str(row['name']).strip(),
                            'description': str(row.get('description', '')).strip() if pd.notna(row.get('description')) else '',
                            'category': category,
                            'manufacturer': str(row.get('manufacturer', '')).strip() if pd.notna(row.get('manufacturer')) else '',
                            'model': str(row.get('model', '')).strip() if pd.notna(row.get('model')) else '',
                            'serial_number': str(row.get('serial_number', '')).strip() if pd.notna(row.get('serial_number')) else None,
                            'status': str(row.get('status', 'available')).strip().lower() if pd.notna(row.get('status')) else 'available',
                            'condition': str(row.get('condition', 'new')).strip().lower() if pd.notna(row.get('condition')) else 'new',
                            'location': location,
                            'vendor': vendor,
                            'purchase_cost': float(row['purchase_cost']) if 'purchase_cost' in df.columns and pd.notna(row.get('purchase_cost')) else None,
                            'notes': str(row.get('notes', '')).strip() if pd.notna(row.get('notes')) else '',
                            'created_by': request.user,
                        }
                    )
                    
                    if created:
                        # Create history
                        AssetHistory.objects.create(
                            asset=asset,
                            action='created',
                            description=f'Asset imported via bulk upload',
                            performed_by=request.user
                        )
                    
                    success_count += 1
                    
                except Exception as e:
                    error_count += 1
                    errors.append(f"Row {index + 2}: {str(e)}")
            
            if success_count > 0:
                messages.success(request, f'Successfully imported {success_count} assets')
            if error_count > 0:
                messages.warning(request, f'{error_count} rows had errors')
                for error in errors[:5]:  # Show first 5 errors
                    messages.error(request, error)
            
            return redirect('assets:asset_list')
            
        except Exception as e:
            messages.error(request, f'Error processing file: {str(e)}')
            return redirect('assets:bulk_import')
    
    context = {}
    return render(request, 'assets/bulk_import.html', context)


@login_required
def download_import_template(request):
    """Download Excel template for bulk import"""
    try:
        import xlsxwriter
        from io import BytesIO
    except ImportError:
        messages.error(request, 'xlsxwriter not installed')
        return redirect('assets:bulk_import')
    
    output = BytesIO()
    workbook = xlsxwriter.Workbook(output)
    worksheet = workbook.add_worksheet('Assets')
    
    # Header format
    header_format = workbook.add_format({
        'bold': True,
        'bg_color': '#4f46e5',
        'font_color': 'white',
        'border': 1,
    })
    
    # Headers
    headers = [
        'asset_tag', 'name', 'description', 'category', 'manufacturer',
        'model', 'serial_number', 'status', 'condition', 'location',
        'vendor', 'purchase_cost', 'notes'
    ]
    
    for col, header in enumerate(headers):
        worksheet.write(0, col, header, header_format)
        worksheet.set_column(col, col, 15)
    
    # Sample data
    sample_data = [
        'AST001', 'Dell Laptop', 'Dell Latitude 5520', 'Laptop', 'Dell',
        'Latitude 5520', 'ABC123XYZ', 'available', 'new', 'Head Office',
        'Dell Technologies', '75000', 'Sample asset'
    ]
    
    for col, value in enumerate(sample_data):
        worksheet.write(1, col, value)
    
    # Add notes
    worksheet.write(3, 0, 'Notes:')
    worksheet.write(4, 0, '- asset_tag and name are required')
    worksheet.write(5, 0, '- status: available, assigned, maintenance, retired')
    worksheet.write(6, 0, '- condition: new, good, fair, poor')
    
    workbook.close()
    output.seek(0)
    
    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="asset_import_template.xlsx"'
    
    return response


@login_required
def bulk_import_employees(request):
    """Bulk import employees from Excel"""
    if request.method == 'POST':
        if 'file' not in request.FILES:
            messages.error(request, 'Please select a file')
            return redirect('assets:bulk_import_employees')
        
        file = request.FILES['file']
        
        try:
            import pandas as pd
            
            df = pd.read_excel(file)
            
            required_cols = ['employee_id', 'first_name', 'last_name', 'email']
            for col in required_cols:
                if col not in df.columns:
                    messages.error(request, f'Missing required column: {col}')
                    return redirect('assets:bulk_import_employees')
            
            success_count = 0
            error_count = 0
            
            for index, row in df.iterrows():
                try:
                    department = None
                    if 'department' in df.columns and pd.notna(row.get('department')):
                        department, _ = Department.objects.get_or_create(
                            name=str(row['department']).strip()
                        )
                    
                    Employee.objects.update_or_create(
                        employee_id=str(row['employee_id']).strip(),
                        defaults={
                            'first_name': str(row['first_name']).strip(),
                            'last_name': str(row['last_name']).strip(),
                            'email': str(row['email']).strip(),
                            'phone': str(row.get('phone', '')).strip() if pd.notna(row.get('phone')) else '',
                            'department': department,
                            'position': str(row.get('position', '')).strip() if pd.notna(row.get('position')) else '',
                            'is_active': True,
                        }
                    )
                    success_count += 1
                except Exception as e:
                    error_count += 1
            
            messages.success(request, f'Imported {success_count} employees, {error_count} errors')
            return redirect('assets:employee_list')
            
        except Exception as e:
            messages.error(request, f'Error: {str(e)}')
    
    return render(request, 'assets/bulk_import_employees.html')


# ============================================
# EMPLOYEES
# ============================================

@login_required
def employee_list(request):
    employees = Employee.objects.select_related('department').annotate(
        asset_count=Count('assets')
    ).all()
    
    search = request.GET.get('search', '')
    if search:
        employees = employees.filter(
            Q(employee_id__icontains=search) |
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(email__icontains=search)
        )
    
    department = request.GET.get('department', '')
    if department:
        employees = employees.filter(department_id=department)
    
    status = request.GET.get('status', '')
    if status == 'active':
        employees = employees.filter(is_active=True)
    elif status == 'inactive':
        employees = employees.filter(is_active=False)
    
    departments = Department.objects.all()
    
    context = {
        'employees': employees,
        'departments': departments,
        'search': search,
        'selected_department': department,
        'selected_status': status,
        'total_count': employees.count(),
    }
    return render(request, 'assets/employee_list.html', context)


@login_required
def employee_detail(request, pk):
    employee = get_object_or_404(Employee, pk=pk)
    assigned_assets = employee.assets.all()
    
    asset_history = AssetHistory.objects.filter(
        Q(new_value__icontains=employee.full_name) |
        Q(old_value__icontains=employee.full_name)
    ).order_by('-created_at')[:10]
    
    context = {
        'employee': employee,
        'assigned_assets': assigned_assets,
        'asset_history': asset_history,
    }
    return render(request, 'assets/employee_detail.html', context)


# ============================================
# PDF REPORTS
# ============================================

@login_required
def generate_asset_pdf(request, pk):
    """Generate PDF report for single asset"""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter, A4
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from io import BytesIO
    except ImportError:
        messages.error(request, 'reportlab not installed. Run: pip install reportlab')
        return redirect('assets:asset_detail', pk=pk)
    
    asset = get_object_or_404(Asset, pk=pk)
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=72)
    
    elements = []
    styles = getSampleStyleSheet()
    
    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        spaceAfter=30,
        textColor=colors.HexColor('#4f46e5')
    )
    elements.append(Paragraph("Asset Report", title_style))
    elements.append(Spacer(1, 20))
    
    # Asset details table
    data = [
        ['Asset Tag', asset.asset_tag],
        ['Name', asset.name],
        ['Category', asset.category.name if asset.category else 'N/A'],
        ['Status', asset.get_status_display()],
        ['Condition', asset.get_condition_display()],
        ['Manufacturer', asset.manufacturer or 'N/A'],
        ['Model', asset.model or 'N/A'],
        ['Serial Number', asset.serial_number or 'N/A'],
        ['Location', str(asset.location) if asset.location else 'N/A'],
        ['Assigned To', asset.assigned_to.full_name if asset.assigned_to else 'Not Assigned'],
        ['Purchase Date', str(asset.purchase_date) if asset.purchase_date else 'N/A'],
        ['Purchase Cost', f'₹{asset.purchase_cost}' if asset.purchase_cost else 'N/A'],
        ['Warranty Expiry', str(asset.warranty_expiry) if asset.warranty_expiry else 'N/A'],
    ]
    
    table = Table(data, colWidths=[2*inch, 4*inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f1f5f9')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e2e8f0')),
    ]))
    elements.append(table)
    
    # History section
    elements.append(Spacer(1, 30))
    elements.append(Paragraph("Asset History", styles['Heading2']))
    elements.append(Spacer(1, 10))
    
    history = asset.history.all()[:10]
    if history:
        history_data = [['Date', 'Action', 'Description', 'By']]
        for h in history:
            history_data.append([
                h.created_at.strftime('%Y-%m-%d %H:%M'),
                h.get_action_display(),
                h.description[:50] if h.description else '',
                h.performed_by.username if h.performed_by else 'System'
            ])
        
        history_table = Table(history_data, colWidths=[1.2*inch, 1*inch, 2.5*inch, 1*inch])
        history_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4f46e5')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e2e8f0')),
        ]))
        elements.append(history_table)
    
    # Footer
    elements.append(Spacer(1, 30))
    footer_style = ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, textColor=colors.grey)
    elements.append(Paragraph(f"Generated on {timezone.now().strftime('%Y-%m-%d %H:%M:%S')} by {request.user.username}", footer_style))
    
    doc.build(elements)
    
    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="asset_{asset.asset_tag}_report.pdf"'
    
    return response


@login_required
def generate_all_assets_pdf(request):
    """Generate PDF report for all assets"""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import inch
        from io import BytesIO
    except ImportError:
        messages.error(request, 'reportlab not installed')
        return redirect('assets:reports')
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    
    elements = []
    styles = getSampleStyleSheet()
    
    # Title
    elements.append(Paragraph("All Assets Report", styles['Heading1']))
    elements.append(Paragraph(f"Generated: {timezone.now().strftime('%Y-%m-%d %H:%M')}", styles['Normal']))
    elements.append(Spacer(1, 20))
    
    # Assets table
    assets = Asset.objects.select_related('category', 'assigned_to', 'location').all()
    
    data = [['Asset Tag', 'Name', 'Category', 'Status', 'Condition', 'Assigned To', 'Location', 'Cost']]
    
    for asset in assets:
        data.append([
            asset.asset_tag,
            asset.name[:30],
            asset.category.name if asset.category else '-',
            asset.get_status_display(),
            asset.get_condition_display(),
            asset.assigned_to.full_name if asset.assigned_to else '-',
            str(asset.location)[:20] if asset.location else '-',
            f'₹{asset.purchase_cost}' if asset.purchase_cost else '-',
        ])
    
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4f46e5')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
    ]))
    elements.append(table)
    
    doc.build(elements)
    
    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="all_assets_report_{timezone.now().strftime("%Y%m%d")}.pdf"'
    
    return response


# ============================================
# EXCEL EXPORT
# ============================================

@login_required
def export_assets(request):
    """Export assets to Excel"""
    try:
        import xlsxwriter
        from io import BytesIO
    except ImportError:
        messages.error(request, 'xlsxwriter not installed')
        return redirect('assets:asset_list')
    
    output = BytesIO()
    workbook = xlsxwriter.Workbook(output)
    worksheet = workbook.add_worksheet('Assets')
    
    # Styles
    header_format = workbook.add_format({
        'bold': True,
        'bg_color': '#4f46e5',
        'font_color': 'white',
        'border': 1,
        'align': 'center',
    })
    
    cell_format = workbook.add_format({'border': 1, 'align': 'left'})
    money_format = workbook.add_format({'border': 1, 'num_format': '₹#,##0.00'})
    date_format = workbook.add_format({'border': 1, 'num_format': 'yyyy-mm-dd'})
    
    headers = [
        'Asset Tag', 'Name', 'Category', 'Status', 'Condition',
        'Manufacturer', 'Model', 'Serial Number', 'Location',
        'Assigned To', 'Assigned Date', 'Vendor', 'Purchase Date',
        'Purchase Cost', 'Warranty Expiry', 'Notes'
    ]
    
    for col, header in enumerate(headers):
        worksheet.write(0, col, header, header_format)
        worksheet.set_column(col, col, 15)
    
    assets = Asset.objects.select_related('category', 'location', 'assigned_to', 'vendor').all()
    
    for row, asset in enumerate(assets, start=1):
        worksheet.write(row, 0, asset.asset_tag, cell_format)
        worksheet.write(row, 1, asset.name, cell_format)
        worksheet.write(row, 2, asset.category.name if asset.category else '', cell_format)
        worksheet.write(row, 3, asset.get_status_display(), cell_format)
        worksheet.write(row, 4, asset.get_condition_display(), cell_format)
        worksheet.write(row, 5, asset.manufacturer or '', cell_format)
        worksheet.write(row, 6, asset.model or '', cell_format)
        worksheet.write(row, 7, asset.serial_number or '', cell_format)
        worksheet.write(row, 8, str(asset.location) if asset.location else '', cell_format)
        worksheet.write(row, 9, asset.assigned_to.full_name if asset.assigned_to else '', cell_format)
        worksheet.write(row, 10, str(asset.assigned_date) if asset.assigned_date else '', date_format)
        worksheet.write(row, 11, asset.vendor.name if asset.vendor else '', cell_format)
        worksheet.write(row, 12, str(asset.purchase_date) if asset.purchase_date else '', date_format)
        worksheet.write(row, 13, float(asset.purchase_cost) if asset.purchase_cost else 0, money_format)
        worksheet.write(row, 14, str(asset.warranty_expiry) if asset.warranty_expiry else '', date_format)
        worksheet.write(row, 15, asset.notes or '', cell_format)
    
    workbook.close()
    output.seek(0)
    
    filename = f'assets_export_{timezone.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    response = HttpResponse(output.read(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    return response


@login_required
def export_employees(request):
    """Export employees to Excel"""
    try:
        import xlsxwriter
        from io import BytesIO
    except ImportError:
        messages.error(request, 'xlsxwriter not installed')
        return redirect('assets:employee_list')
    
    output = BytesIO()
    workbook = xlsxwriter.Workbook(output)
    worksheet = workbook.add_worksheet('Employees')
    
    header_format = workbook.add_format({
        'bold': True,
        'bg_color': '#4f46e5',
        'font_color': 'white',
        'border': 1,
    })
    
    cell_format = workbook.add_format({'border': 1})
    
    headers = ['Employee ID', 'First Name', 'Last Name', 'Email', 'Phone', 
               'Department', 'Position', 'Status', 'Hire Date', 'Assets Count']
    
    for col, header in enumerate(headers):
        worksheet.write(0, col, header, header_format)
        worksheet.set_column(col, col, 15)
    
    employees = Employee.objects.select_related('department').annotate(asset_count=Count('assets')).all()
    
    for row, emp in enumerate(employees, start=1):
        worksheet.write(row, 0, emp.employee_id, cell_format)
        worksheet.write(row, 1, emp.first_name, cell_format)
        worksheet.write(row, 2, emp.last_name, cell_format)
        worksheet.write(row, 3, emp.email, cell_format)
        worksheet.write(row, 4, emp.phone or '', cell_format)
        worksheet.write(row, 5, emp.department.name if emp.department else '', cell_format)
        worksheet.write(row, 6, emp.position or '', cell_format)
        worksheet.write(row, 7, 'Active' if emp.is_active else 'Inactive', cell_format)
        worksheet.write(row, 8, str(emp.hire_date) if emp.hire_date else '', cell_format)
        worksheet.write(row, 9, emp.asset_count, cell_format)
    
    workbook.close()
    output.seek(0)
    
    filename = f'employees_export_{timezone.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    response = HttpResponse(output.read(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    return response


# ============================================
# EMAIL NOTIFICATIONS
# ============================================

def send_assignment_email(asset, employee, assigned_by):
    """Send email when asset is assigned"""
    subject = f'Asset Assigned: {asset.asset_tag}'
    
    message = f"""
Dear {employee.full_name},

An IT asset has been assigned to you.

Asset Details:
- Asset Tag: {asset.asset_tag}
- Name: {asset.name}
- Category: {asset.category.name if asset.category else 'N/A'}
- Serial Number: {asset.serial_number or 'N/A'}
- Assigned Date: {asset.assigned_date}
- Assigned By: {assigned_by.username}

Please take good care of this equipment. If you have any questions, please contact the IT department.

Best regards,
IT Asset Management System
"""
    
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [employee.email],
        fail_silently=False,
    )


def send_unassignment_email(asset, employee, unassigned_by):
    """Send email when asset is unassigned"""
    subject = f'Asset Returned: {asset.asset_tag}'
    
    message = f"""
Dear {employee.full_name},

The following IT asset has been unassigned from you:

- Asset Tag: {asset.asset_tag}
- Name: {asset.name}
- Unassigned By: {unassigned_by.username}
- Date: {timezone.now().strftime('%Y-%m-%d')}

If you still have this asset, please return it to the IT department.

Best regards,
IT Asset Management System
"""
    
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [employee.email],
        fail_silently=False,
    )


@login_required
def send_warranty_alerts(request):
    """Send warranty expiry alerts"""
    thirty_days = timezone.now().date() + timedelta(days=30)
    
    expiring_assets = Asset.objects.filter(
        warranty_expiry__lte=thirty_days,
        warranty_expiry__gte=timezone.now().date()
    ).select_related('assigned_to')
    
    if not expiring_assets:
        messages.info(request, 'No assets with expiring warranties')
        return redirect('assets:reports')
    
    # Send to admin
    subject = f'Warranty Alert: {expiring_assets.count()} assets expiring soon'
    
    message = "The following assets have warranties expiring within 30 days:\n\n"
    for asset in expiring_assets:
        message += f"- {asset.asset_tag} - {asset.name} - Expires: {asset.warranty_expiry}\n"
    
    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [request.user.email],
            fail_silently=False,
        )
        messages.success(request, f'Warranty alert sent to {request.user.email}')
    except Exception as e:
        messages.error(request, f'Failed to send email: {str(e)}')
    
    return redirect('assets:reports')


# ============================================
# REPORTS
# ============================================

@login_required
def reports(request):
    total_assets = Asset.objects.count()
    total_value = Asset.objects.aggregate(total=Sum('purchase_cost'))['total'] or 0
    
    status_counts = Asset.objects.values('status').annotate(count=Count('id'))
    
    category_counts = Category.objects.annotate(
        count=Count('asset'),
        total_value=Sum('asset__purchase_cost')
    ).filter(count__gt=0)
    
    location_counts = Location.objects.annotate(count=Count('asset')).filter(count__gt=0)
    
    department_counts = Department.objects.annotate(
        asset_count=Count('employee__assets')
    ).filter(asset_count__gt=0)
    
    today = timezone.now().date()
    thirty_days = today + timedelta(days=30)
    
    warranty_valid = Asset.objects.filter(warranty_expiry__gte=today).count()
    warranty_expiring = Asset.objects.filter(
        warranty_expiry__gte=today,
        warranty_expiry__lte=thirty_days
    ).count()
    warranty_expired = Asset.objects.filter(warranty_expiry__lt=today).count()
    
    context = {
        'total_assets': total_assets,
        'total_value': total_value,
        'status_counts': status_counts,
        'category_counts': category_counts,
        'location_counts': location_counts,
        'department_counts': department_counts,
        'warranty_valid': warranty_valid,
        'warranty_expiring': warranty_expiring,
        'warranty_expired': warranty_expired,
    }
    return render(request, 'assets/reports.html', context)


# ============================================
# MAINTENANCE & HISTORY
# ============================================

@login_required
def maintenance_list(request):
    records = MaintenanceRecord.objects.select_related('asset').all()
    
    status = request.GET.get('status', '')
    if status:
        records = records.filter(status=status)
    
    mtype = request.GET.get('type', '')
    if mtype:
        records = records.filter(maintenance_type=mtype)
    
    context = {
        'records': records,
        'selected_status': status,
        'selected_type': mtype,
    }
    return render(request, 'assets/maintenance_list.html', context)


@login_required
def history_list(request):
    history = AssetHistory.objects.select_related('asset', 'performed_by').all()
    
    action = request.GET.get('action', '')
    if action:
        history = history.filter(action=action)
    
    search = request.GET.get('search', '')
    if search:
        history = history.filter(
            Q(asset__asset_tag__icontains=search) |
            Q(asset__name__icontains=search) |
            Q(description__icontains=search)
        )
    
    context = {
        'history': history[:100],
        'selected_action': action,
        'search': search,
    }
    return render(request, 'assets/history_list.html', context)


# ============================================
# USER MANAGEMENT
# ============================================

def is_admin(user):
    return user.is_superuser or user.groups.filter(name='Admin').exists()


@login_required
@user_passes_test(is_admin)
def user_list(request):
    """List all users (admin only)"""
    users = User.objects.all().order_by('-date_joined')
    groups = Group.objects.all()
    
    context = {
        'users': users,
        'groups': groups,
    }
    return render(request, 'assets/user_list.html', context)


@login_required
@user_passes_test(is_admin)
def user_detail(request, pk):
    """View user details (admin only)"""
    user_obj = get_object_or_404(User, pk=pk)
    
    # Get user's activity
    activity = AssetHistory.objects.filter(performed_by=user_obj).order_by('-created_at')[:20]
    
    context = {
        'user_obj': user_obj,
        'activity': activity,
        'groups': Group.objects.all(),
    }
    return render(request, 'assets/user_detail.html', context)


@login_required
@user_passes_test(is_admin)
def user_toggle_active(request, pk):
    """Toggle user active status"""
    user_obj = get_object_or_404(User, pk=pk)
    
    if user_obj == request.user:
        messages.error(request, "You cannot deactivate yourself")
        return redirect('assets:user_list')
    
    user_obj.is_active = not user_obj.is_active
    user_obj.save()
    
    status = "activated" if user_obj.is_active else "deactivated"
    messages.success(request, f"User {user_obj.username} has been {status}")
    
    return redirect('assets:user_list')


@login_required
@user_passes_test(is_admin)
def user_change_role(request, pk):
    """Change user role/group"""
    if request.method == 'POST':
        user_obj = get_object_or_404(User, pk=pk)
        group_id = request.POST.get('group_id')
        
        # Clear existing groups
        user_obj.groups.clear()
        
        if group_id:
            group = get_object_or_404(Group, pk=group_id)
            user_obj.groups.add(group)
            messages.success(request, f"User {user_obj.username} added to {group.name} group")
        else:
            messages.success(request, f"User {user_obj.username} removed from all groups")
    
    return redirect('assets:user_detail', pk=pk)


@login_required
@user_passes_test(is_admin)
def create_user(request):
    """Create new user"""
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        first_name = request.POST.get('first_name', '')
        last_name = request.POST.get('last_name', '')
        is_staff = request.POST.get('is_staff', False)
        group_id = request.POST.get('group_id')
        
        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username already exists')
            return redirect('assets:create_user')
        
        if User.objects.filter(email=email).exists():
            messages.error(request, 'Email already exists')
            return redirect('assets:create_user')
        
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            is_staff=bool(is_staff),
        )
        
        if group_id:
            group = get_object_or_404(Group, pk=group_id)
            user.groups.add(group)
        
        messages.success(request, f'User {username} created successfully')
        return redirect('assets:user_list')
    
    context = {
        'groups': Group.objects.all(),
    }
    return render(request, 'assets/create_user.html', context)


@login_required
@user_passes_test(is_admin)
def setup_roles(request):
    """Setup default user roles/groups"""
    roles = [
        {'name': 'Admin', 'description': 'Full access to all features'},
        {'name': 'Manager', 'description': 'Can manage assets and employees'},
        {'name': 'Technician', 'description': 'Can update asset status and maintenance'},
        {'name': 'Viewer', 'description': 'Read-only access'},
    ]
    
    for role in roles:
        Group.objects.get_or_create(name=role['name'])
    
    messages.success(request, 'Default roles created: Admin, Manager, Technician, Viewer')
    return redirect('assets:user_list')

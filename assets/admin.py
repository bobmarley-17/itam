from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Count
from .models import (
    Department, Employee, Category, Location, 
    Vendor, Asset, AssetHistory, MaintenanceRecord
)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ['name', 'description', 'employee_count', 'created_at']
    search_fields = ['name']
    
    def employee_count(self, obj):
        return obj.employee_count
    employee_count.short_description = 'Employees'
    employee_count.admin_order_field = 'employee_count'

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.annotate(employee_count=Count('employee'))


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ['employee_id', 'full_name', 'email', 'department', 'position', 'is_active', 'asset_count']
    list_filter = ['is_active', 'department']
    search_fields = ['employee_id', 'first_name', 'last_name', 'email']
    list_editable = ['is_active']
    list_select_related = ('department',)
    
    def full_name(self, obj):
        return obj.full_name
    full_name.short_description = 'Name'
    
    def asset_count(self, obj):
        count = obj.asset_count
        if count > 0:
            return format_html('<span style="color: green; font-weight: bold;">{}</span>', count)
        return count
    asset_count.short_description = 'Assets'
    asset_count.admin_order_field = 'asset_count'

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.annotate(asset_count=Count('assets'))


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'icon_display', 'description', 'asset_count']
    search_fields = ['name']
    
    def icon_display(self, obj):
        return format_html('<i class="{}"></i> {}', obj.icon, obj.icon)
    icon_display.short_description = 'Icon'
    
    def asset_count(self, obj):
        return obj.asset_count
    asset_count.short_description = 'Assets'
    asset_count.admin_order_field = 'asset_count'

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.annotate(asset_count=Count('asset'))


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ['name', 'building', 'floor', 'room', 'asset_count']
    list_filter = ['building']
    search_fields = ['name', 'building']
    
    def asset_count(self, obj):
        return obj.asset_count
    asset_count.short_description = 'Assets'
    asset_count.admin_order_field = 'asset_count'

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.annotate(asset_count=Count('asset'))


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ['name', 'contact_person', 'email', 'phone', 'asset_count']
    search_fields = ['name', 'contact_person', 'email']

    def asset_count(self, obj):
        return obj.asset_count
    asset_count.short_description = 'Assets Purchased'
    asset_count.admin_order_field = 'asset_count'

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.annotate(asset_count=Count('asset'))


class AssetHistoryInline(admin.TabularInline):
    model = AssetHistory
    extra = 0
    readonly_fields = ['action', 'description', 'performed_by', 'old_value', 'new_value', 'created_at']
    can_delete = False
    
    def has_add_permission(self, request, obj=None):
        return False


class MaintenanceRecordInline(admin.TabularInline):
    model = MaintenanceRecord
    extra = 0
    fields = ['maintenance_type', 'status', 'scheduled_date', 'completed_date', 'cost']


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = [
        'asset_tag', 'name', 'category', 'status_badge', 
        'condition', 'assigned_to', 'location', 'warranty_status'
    ]
    list_filter = ['status', 'condition', 'category', 'location', 'vendor']
    search_fields = ['asset_tag', 'name', 'serial_number', 'assigned_to__first_name', 'assigned_to__last_name']
    list_editable = ['condition']
    list_select_related = ('category', 'assigned_to', 'location')
    readonly_fields = ['created_at', 'updated_at', 'created_by']
    date_hierarchy = 'purchase_date'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('asset_tag', 'name', 'description', 'category')
        }),
        ('Specifications', {
            'fields': ('manufacturer', 'model', 'serial_number')
        }),
        ('Status & Location', {
            'fields': ('status', 'condition', 'location')
        }),
        ('Assignment', {
            'fields': ('assigned_to', 'assigned_date'),
            'classes': ('collapse',)
        }),
        ('Purchase Information', {
            'fields': ('vendor', 'purchase_date', 'purchase_cost', 'warranty_expiry'),
            'classes': ('collapse',)
        }),
        ('Additional Info', {
            'fields': ('notes', 'created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    inlines = [MaintenanceRecordInline, AssetHistoryInline]
    
    def status_badge(self, obj):
        colors = {
            'available': '#10b981',
            'assigned': '#3b82f6',
            'maintenance': '#f59e0b',
            'retired': '#6b7280',
            'lost': '#ef4444',
        }
        color = colors.get(obj.status, '#6b7280')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; '
            'border-radius: 15px; font-size: 11px; font-weight: bold;">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    def warranty_status(self, obj):
        if obj.is_under_warranty:
            return format_html('<span style="color: green;">✓ Valid</span>')
        elif obj.warranty_expiry:
            return format_html('<span style="color: red;">✗ Expired</span>')
        return format_html('<span style="color: gray;">N/A</span>')
    warranty_status.short_description = 'Warranty'
    
    def save_model(self, request, obj, form, change):
        if not obj.pk:  # When creating a new object, pk is None.
            obj.created_by = request.user

        super().save_model(request, obj, form, change)

        # Log history for creation or changes
        action_type = 'created' if not change else 'updated'
        description = ''

        if not change:
            description = f'Asset {obj.asset_tag} was created.'
        elif form.changed_data:
            changed_fields = ', '.join(form.changed_data)
            description = f'Fields updated: {changed_fields}.'

        if description:  # Only create a history record if something happened
            AssetHistory.objects.create(
                asset=obj,
                action=action_type,
                description=description,
                performed_by=request.user
            )


@admin.register(AssetHistory)
class AssetHistoryAdmin(admin.ModelAdmin):
    list_display = ['asset', 'action', 'description', 'performed_by', 'created_at']
    list_filter = ['action', 'created_at']
    search_fields = ['asset__asset_tag', 'asset__name', 'description']
    readonly_fields = ['asset', 'action', 'description', 'performed_by', 'old_value', 'new_value', 'created_at']
    date_hierarchy = 'created_at'
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False


@admin.register(MaintenanceRecord)
class MaintenanceRecordAdmin(admin.ModelAdmin):
    list_display = ['asset', 'maintenance_type', 'status_badge', 'scheduled_date', 'completed_date', 'cost']
    list_filter = ['status', 'maintenance_type', 'scheduled_date']
    search_fields = ['asset__asset_tag', 'asset__name', 'description']
    list_select_related = ('asset',)
    date_hierarchy = 'scheduled_date'
    
    def status_badge(self, obj):
        colors = {
            'scheduled': '#3b82f6',
            'in_progress': '#f59e0b',
            'completed': '#10b981',
            'cancelled': '#6b7280',
        }
        color = colors.get(obj.status, '#6b7280')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; '
            'border-radius: 15px; font-size: 11px;">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = 'Status'


# Customize Admin Site
admin.site.site_header = "IT Asset Management"
admin.site.site_title = "IT Asset Admin"
admin.site.index_title = "Welcome to Asset Management System"

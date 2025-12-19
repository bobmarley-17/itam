from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Department(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name
    
    class Meta:
        ordering = ['name']


class Employee(models.Model):
    employee_id = models.CharField(max_length=50, unique=True, default='EMP000')
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True)
    position = models.CharField(max_length=100, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    hire_date = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.employee_id})"
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"
    
    class Meta:
        ordering = ['first_name', 'last_name']


class Category(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    icon = models.CharField(max_length=50, default='fas fa-box')
    
    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['name']


class Location(models.Model):
    name = models.CharField(max_length=100)
    building = models.CharField(max_length=100, blank=True, null=True)
    floor = models.CharField(max_length=20, blank=True, null=True)
    room = models.CharField(max_length=50, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    
    def __str__(self):
        parts = [self.name]
        if self.building:
            parts.append(self.building)
        if self.floor:
            parts.append(f"Floor {self.floor}")
        return " - ".join(parts)
    
    class Meta:
        ordering = ['name']


class Vendor(models.Model):
    name = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=100, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    website = models.URLField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name
    
    class Meta:
        ordering = ['name']


class Asset(models.Model):
    STATUS_CHOICES = [
        ('available', 'Available'),
        ('assigned', 'Assigned'),
        ('maintenance', 'Under Maintenance'),
        ('retired', 'Retired'),
        ('lost', 'Lost/Stolen'),
    ]
    
    CONDITION_CHOICES = [
        ('new', 'New'),
        ('good', 'Good'),
        ('fair', 'Fair'),
        ('poor', 'Poor'),
    ]
    
    # Basic Info
    asset_tag = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Specifications
    manufacturer = models.CharField(max_length=100, blank=True, null=True)
    model = models.CharField(max_length=100, blank=True, null=True)
    serial_number = models.CharField(max_length=100, blank=True, null=True)
    
    # Status & Location
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')
    condition = models.CharField(max_length=20, choices=CONDITION_CHOICES, default='new')
    location = models.ForeignKey(Location, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Assignment
    assigned_to = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='assets')
    assigned_date = models.DateField(blank=True, null=True)
    
    # Purchase Info
    vendor = models.ForeignKey(Vendor, on_delete=models.SET_NULL, null=True, blank=True)
    purchase_date = models.DateField(blank=True, null=True)
    purchase_cost = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    warranty_expiry = models.DateField(blank=True, null=True)
    
    # Additional Info
    notes = models.TextField(blank=True, null=True)
    
    # Timestamps
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_assets')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.asset_tag} - {self.name}"
    
    @property
    def is_under_warranty(self):
        if self.warranty_expiry:
            return self.warranty_expiry >= timezone.now().date()
        return False
    
    class Meta:
        ordering = ['-created_at']


class AssetHistory(models.Model):
    ACTION_CHOICES = [
        ('created', 'Created'),
        ('assigned', 'Assigned'),
        ('unassigned', 'Unassigned'),
        ('maintenance', 'Sent to Maintenance'),
        ('returned', 'Returned from Maintenance'),
        ('retired', 'Retired'),
        ('updated', 'Updated'),
        ('location_changed', 'Location Changed'),
    ]
    
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name='history')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    description = models.TextField(blank=True, null=True)
    performed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    old_value = models.CharField(max_length=255, blank=True, null=True)
    new_value = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.asset.asset_tag} - {self.action} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"
    
    class Meta:
        verbose_name_plural = "Asset Histories"
        ordering = ['-created_at']


class MaintenanceRecord(models.Model):
    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    TYPE_CHOICES = [
        ('repair', 'Repair'),
        ('upgrade', 'Upgrade'),
        ('inspection', 'Inspection'),
        ('cleaning', 'Cleaning'),
        ('other', 'Other'),
    ]
    
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name='maintenance_records')
    maintenance_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')
    description = models.TextField()
    scheduled_date = models.DateField()
    completed_date = models.DateField(blank=True, null=True)
    cost = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    performed_by = models.CharField(max_length=100, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.asset.asset_tag} - {self.maintenance_type} - {self.scheduled_date}"
    
    class Meta:
        ordering = ['-scheduled_date']

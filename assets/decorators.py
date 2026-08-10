from django.core.exceptions import PermissionDenied

def group_required(*group_names):
    """
    Decorator for views that requires user to be in at least one of the
    specified groups. Also allows superusers.
    """
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            if request.user.is_superuser or (request.user.groups.filter(name__in=group_names).exists()):
                return view_func(request, *args, **kwargs)
            raise PermissionDenied
        return wrapper
    return decorator

admin_required = group_required('Admin')
manager_required = group_required('Admin', 'Manager')
technician_required = group_required('Admin', 'Manager', 'Technician')
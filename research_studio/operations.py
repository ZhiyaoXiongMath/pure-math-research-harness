"""Explicit operational entry points; readers never advance or recover work."""
from . import views


def status(store,instance_id=None):
    return views.status(store.read_snapshot(),store,instance_id=instance_id)


def export_project(store,out):
    from .portability import export_project as export_native
    return export_native(store,out)


def restore(source,out):
    from .portability import restore as restore_native
    return restore_native(source,out)

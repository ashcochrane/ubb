import os
import uuid

from celery import Celery
from celery.signals import before_task_publish, task_prerun

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('ubb_platform')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()


@before_task_publish.connect
def propagate_correlation_id(headers=None, **kwargs):
    if headers is None:
        return
    from core.logging import correlation_id_var
    cid = correlation_id_var.get("")
    if cid:
        headers["correlation_id"] = cid


@task_prerun.connect
def restore_correlation_id(task=None, **kwargs):
    from core.logging import correlation_id_var
    cid = getattr(task.request, "correlation_id", None)
    if not cid:
        # Periodic tasks or retries without header — generate fresh ID
        cid = str(uuid.uuid4())
    correlation_id_var.set(cid)

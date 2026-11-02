"""The one configured Celery application, loaded by every process that loads Django.

`config.celery` builds the app from `settings` (broker, queues, schedule). The worker and
beat load it because they are started with `-A config`; the WEB process never did — it
imports `config.wsgi`/`config.urls`, never `config.celery` — so every `shared_task.delay()`
issued from a web request bound to Celery's DEFAULT app, which has no broker: each one
failed (`outbox.dispatch_failed`) and delivery fell back to the minutely outbox sweep.
Found by the W7 preparation pass (finding F1) and fixed here by the conventional
Django/Celery wiring: importing the app from the project package makes it the current app
for every `shared_task` in any process that imports `config`, which every Django process
does through `DJANGO_SETTINGS_MODULE`.
"""
from .celery import app as celery_app

__all__ = ("celery_app",)

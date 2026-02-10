"""Stub -- full implementation in Task 4."""
from celery import shared_task


@shared_task(queue="ubb_events")
def process_single_event(event_id):
    pass

"""The usage app's scheduled work: the daily measurement prune (W5).

`config/settings.py`'s `CELERY_BEAT_SCHEDULE` runs it once a day; the job and
its rules are `pruning.py`'s.
"""
from celery import shared_task

from apps.metering.usage.pruning import prune_measurements


@shared_task(queue="ubb_metering")
def prune_measurement_detail():
    """Release and delete the measurement records older than the measurement
    horizon whose postings are resolved. Returns the run's result as plain
    data; the run's one structured log line carries the same."""
    return prune_measurements().as_data()

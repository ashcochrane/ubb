from django.conf import settings


class TestCeleryConfig:
    def test_ubb_events_queue_exists(self):
        queue_names = [q.name for q in settings.CELERY_TASK_QUEUES]
        assert "ubb_events" in queue_names

    def test_sweep_outbox_in_beat_schedule(self):
        assert "sweep-outbox" in settings.CELERY_BEAT_SCHEDULE

    def test_cleanup_outbox_in_beat_schedule(self):
        assert "cleanup-outbox" in settings.CELERY_BEAT_SCHEDULE

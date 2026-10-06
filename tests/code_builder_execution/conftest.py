"""What every execution test stands on: the platform's own test guards, and
the real application, served.

**The platform's two guards, loaded from the platform's own conftest** rather
than copied here, so they cannot drift apart: the suite runs on Redis DB 15
(`UBB_TEST_REDIS_DB` moves it, for a run beside another), and no test reaches
Stripe. The application served to a generated file is in this process, so the
Stripe guard holds for it too.

**The application** is pytest-django's `live_server`, the real router,
database and economic services. Every test using it is
`django_db(transaction=True)`, so what the server writes is committed and
the test reads it back. One thing is switched off, as the platform's own
live-server tests switch it off: the outbox's dispatch to Celery, which has
no worker here. It is fire-and-forget fan-out, run after the response is
built; nothing a generated file is answered with depends on it.
"""
import importlib.util
from unittest.mock import patch

import pytest

from _harness import CONTAINER_HOST, REPO_ROOT, Server

_spec = importlib.util.spec_from_file_location(
    "ubb_platform_root_conftest", REPO_ROOT / "ubb-platform" / "conftest.py")
_platform = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_platform)

#: The platform's own hooks, by their own names, so pytest runs them here.
pytest_configure = _platform.pytest_configure
_stripe_guard = _platform._stripe_guard

#: Where the outbox hands an event to Celery.
OUTBOX_DISPATCH = "apps.platform.events.tasks.process_single_event.delay"


@pytest.fixture
def server(live_server, settings):
    """The live application, reachable from this machine and from a
    container. A container on Docker Desktop calls this machine by another
    name, and the application must accept that name as a host."""
    served = Server(url=live_server.url)
    if not served.shares_the_network:
        settings.ALLOWED_HOSTS = [*settings.ALLOWED_HOSTS, CONTAINER_HOST]
    with patch(OUTBOX_DISPATCH):
        yield served

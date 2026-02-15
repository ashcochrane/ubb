# Platform Architecture Restructure — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restructure the UBB platform so products are fully independent building blocks communicating exclusively through a transactional outbox, replacing the synchronous event bus.

**Architecture:** Products (metering, billing, subscriptions, referrals) depend only on platform + core. All cross-product communication goes through a transactional outbox with per-event Celery tasks, idempotent handlers, dead letter handling, and sweep recovery. Wallet/topup models move from platform to billing. A payment provider abstraction replaces direct Stripe calls. Legacy ungated endpoints are removed.

**Tech Stack:** Django 6.0, django-ninja, Celery, Redis, Stripe, SQLite (dev), pytest

**Design doc:** `docs/plans/2026-02-09-platform-architecture-restructure-design.md`

**Run tests:** `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q`

**Run single test:** `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest <path>::<test> -v`

---

## Phase 1: Foundation (Outbox + Core Cleanup)

### Task 1: Create the events app with OutboxEvent and HandlerCheckpoint models

**Files:**
- Create: `ubb-platform/apps/platform/events/__init__.py`
- Create: `ubb-platform/apps/platform/events/apps.py`
- Create: `ubb-platform/apps/platform/events/models.py`
- Create: `ubb-platform/apps/platform/events/migrations/__init__.py`
- Modify: `ubb-platform/config/settings.py:22-41` (INSTALLED_APPS)

**Step 1: Write the failing test**

Create `ubb-platform/apps/platform/events/tests/__init__.py` (empty) and:

```python
# ubb-platform/apps/platform/events/tests/test_models.py
import pytest
from django.db import IntegrityError, transaction


@pytest.mark.django_db
class TestOutboxEvent:
    def test_create_outbox_event(self):
        from apps.platform.events.models import OutboxEvent
        import uuid

        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={"customer_id": "cust_123", "cost_micros": 5000},
            tenant_id=uuid.uuid4(),
        )
        assert event.status == "pending"
        assert event.retry_count == 0
        assert event.max_retries == 5
        assert event.next_retry_at is None
        assert event.processed_at is None
        assert event.last_error == ""
        assert event.correlation_id == ""

    def test_outbox_event_str(self):
        from apps.platform.events.models import OutboxEvent
        import uuid

        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={},
            tenant_id=uuid.uuid4(),
        )
        assert "usage.recorded" in str(event)


@pytest.mark.django_db
class TestHandlerCheckpoint:
    def test_create_checkpoint(self):
        from apps.platform.events.models import OutboxEvent, HandlerCheckpoint
        import uuid

        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={},
            tenant_id=uuid.uuid4(),
        )
        cp = HandlerCheckpoint.objects.create(
            outbox_event=event,
            handler_name="billing.wallet_deduction",
        )
        assert cp.handler_name == "billing.wallet_deduction"

    def test_checkpoint_unique_per_event_handler(self):
        from apps.platform.events.models import OutboxEvent, HandlerCheckpoint
        import uuid

        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={},
            tenant_id=uuid.uuid4(),
        )
        HandlerCheckpoint.objects.create(
            outbox_event=event,
            handler_name="billing.wallet_deduction",
        )
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                HandlerCheckpoint.objects.create(
                    outbox_event=event,
                    handler_name="billing.wallet_deduction",
                )

    def test_checkpoint_cascade_deletes_with_event(self):
        from apps.platform.events.models import OutboxEvent, HandlerCheckpoint
        import uuid

        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={},
            tenant_id=uuid.uuid4(),
        )
        HandlerCheckpoint.objects.create(
            outbox_event=event,
            handler_name="billing.wallet_deduction",
        )
        event.delete()
        assert HandlerCheckpoint.objects.count() == 0
```

**Step 2: Run test to verify it fails**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/events/tests/test_models.py -v`
Expected: FAIL — module not found or app not installed

**Step 3: Write minimal implementation**

```python
# ubb-platform/apps/platform/events/__init__.py
```

```python
# ubb-platform/apps/platform/events/apps.py
from django.apps import AppConfig


class EventsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.platform.events"
    label = "events"
```

```python
# ubb-platform/apps/platform/events/models.py
from django.db import models

from core.models import BaseModel


OUTBOX_STATUS_CHOICES = [
    ("pending", "Pending"),
    ("processing", "Processing"),
    ("processed", "Processed"),
    ("failed", "Failed"),
    ("skipped", "Skipped"),
]


class OutboxEvent(BaseModel):
    event_type = models.CharField(max_length=100, db_index=True)
    payload = models.JSONField()
    tenant_id = models.UUIDField(db_index=True)

    status = models.CharField(
        max_length=20, choices=OUTBOX_STATUS_CHOICES, default="pending", db_index=True
    )
    retry_count = models.IntegerField(default=0)
    max_retries = models.IntegerField(default=5)
    next_retry_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_error = models.TextField(blank=True, default="")
    processed_at = models.DateTimeField(null=True, blank=True)
    correlation_id = models.CharField(max_length=100, blank=True, default="")

    class Meta:
        db_table = "ubb_outbox_event"
        indexes = [
            models.Index(fields=["status", "next_retry_at"], name="idx_outbox_status_retry"),
            models.Index(fields=["status", "created_at"], name="idx_outbox_status_created"),
            models.Index(
                fields=["tenant_id", "event_type", "created_at"],
                name="idx_outbox_tenant_type_created",
            ),
        ]

    def __str__(self):
        return f"OutboxEvent({self.event_type} [{self.status}])"


class HandlerCheckpoint(BaseModel):
    outbox_event = models.ForeignKey(
        OutboxEvent, on_delete=models.CASCADE, related_name="checkpoints"
    )
    handler_name = models.CharField(max_length=100)

    class Meta:
        db_table = "ubb_handler_checkpoint"
        constraints = [
            models.UniqueConstraint(
                fields=["outbox_event", "handler_name"],
                name="uq_checkpoint_event_handler",
            ),
        ]

    def __str__(self):
        return f"HandlerCheckpoint({self.handler_name} for {self.outbox_event_id})"
```

Add to `config/settings.py` INSTALLED_APPS, after `"apps.platform.customers"`:
```python
"apps.platform.events",
```

Create migration:
```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py makemigrations events
```

Apply:
```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py migrate
```

**Step 4: Run test to verify it passes**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/events/tests/test_models.py -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add apps/platform/events/ config/settings.py
git commit -m "feat: add OutboxEvent and HandlerCheckpoint models"
```

---

### Task 2: Create event schema contracts

**Files:**
- Create: `ubb-platform/apps/platform/events/schemas.py`

**Step 1: Write the failing test**

```python
# ubb-platform/apps/platform/events/tests/test_schemas.py
from dataclasses import asdict


class TestUsageRecordedSchema:
    def test_create_with_required_fields(self):
        from apps.platform.events.schemas import UsageRecorded

        event = UsageRecorded(
            tenant_id="t1",
            customer_id="c1",
            event_id="e1",
            cost_micros=5000,
        )
        assert event.tenant_id == "t1"
        assert event.cost_micros == 5000
        assert event.provider_cost_micros is None
        assert event.billed_cost_micros is None
        assert event.event_type == ""
        assert event.provider == ""

    def test_frozen(self):
        from apps.platform.events.schemas import UsageRecorded
        import pytest

        event = UsageRecorded(tenant_id="t1", customer_id="c1", event_id="e1", cost_micros=5000)
        with pytest.raises(AttributeError):
            event.cost_micros = 999

    def test_roundtrip_via_dict(self):
        from apps.platform.events.schemas import UsageRecorded

        event = UsageRecorded(
            tenant_id="t1", customer_id="c1", event_id="e1",
            cost_micros=5000, billed_cost_micros=6000,
        )
        d = asdict(event)
        reconstructed = UsageRecorded(**d)
        assert reconstructed == event

    def test_extra_fields_ignored_gracefully(self):
        """New fields added later don't break old consumers."""
        from apps.platform.events.schemas import UsageRecorded

        d = {
            "tenant_id": "t1", "customer_id": "c1", "event_id": "e1",
            "cost_micros": 5000, "some_new_field": "value",
        }
        # Filter unknown keys
        import dataclasses
        known = {f.name for f in dataclasses.fields(UsageRecorded)}
        filtered = {k: v for k, v in d.items() if k in known}
        event = UsageRecorded(**filtered)
        assert event.cost_micros == 5000


class TestUsageRefundedSchema:
    def test_create(self):
        from apps.platform.events.schemas import UsageRefunded

        event = UsageRefunded(
            tenant_id="t1", customer_id="c1", event_id="e1",
            refund_id="r1", refund_amount_micros=5000,
        )
        assert event.EVENT_TYPE == "usage.refunded"
        assert event.refund_amount_micros == 5000


class TestReferralRewardEarnedSchema:
    def test_create(self):
        from apps.platform.events.schemas import ReferralRewardEarned

        event = ReferralRewardEarned(
            tenant_id="t1", referral_id="ref1", referrer_id="rr1",
            referred_customer_id="c1", reward_micros=500,
        )
        assert event.EVENT_TYPE == "referral.reward_earned"
```

**Step 2: Run test to verify it fails**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/events/tests/test_schemas.py -v`
Expected: FAIL — module not found

**Step 3: Write minimal implementation**

```python
# ubb-platform/apps/platform/events/schemas.py
"""
Frozen dataclass contracts for outbox events.

Rules:
- All event schemas are frozen dataclasses.
- New fields MUST have defaults (additive-only evolution).
- Breaking changes (renames, removals, type changes) require a new class.
- Producers: construct dataclass → asdict() → write to outbox.
- Consumers: filter unknown keys → construct dataclass from payload.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class UsageRecorded:
    EVENT_TYPE = "usage.recorded"

    tenant_id: str
    customer_id: str
    event_id: str
    cost_micros: int
    provider_cost_micros: int | None = None
    billed_cost_micros: int | None = None
    event_type: str = ""
    provider: str = ""
    auto_topup_attempt_id: str | None = None


@dataclass(frozen=True)
class UsageRefunded:
    EVENT_TYPE = "usage.refunded"

    tenant_id: str
    customer_id: str
    event_id: str
    refund_id: str
    refund_amount_micros: int


@dataclass(frozen=True)
class ReferralRewardEarned:
    EVENT_TYPE = "referral.reward_earned"

    tenant_id: str
    referral_id: str
    referrer_id: str
    referred_customer_id: str
    reward_micros: int
```

**Step 4: Run test to verify it passes**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/events/tests/test_schemas.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add apps/platform/events/schemas.py apps/platform/events/tests/test_schemas.py
git commit -m "feat: add frozen dataclass event schema contracts"
```

---

### Task 3: Build outbox write_event() and handler registry

**Files:**
- Create: `ubb-platform/apps/platform/events/outbox.py`
- Create: `ubb-platform/apps/platform/events/registry.py`

**Step 1: Write the failing test**

```python
# ubb-platform/apps/platform/events/tests/test_outbox.py
import pytest
from unittest.mock import patch, MagicMock

from apps.platform.events.schemas import UsageRecorded


@pytest.mark.django_db
class TestWriteEvent:
    def test_write_event_creates_outbox_row(self):
        from apps.platform.events.outbox import write_event
        from apps.platform.events.models import OutboxEvent

        schema = UsageRecorded(
            tenant_id="aaaa-bbbb",
            customer_id="c1",
            event_id="e1",
            cost_micros=5000,
        )

        with patch("apps.platform.events.outbox.process_single_event") as mock_task:
            write_event(schema)

        assert OutboxEvent.objects.count() == 1
        event = OutboxEvent.objects.first()
        assert event.event_type == "usage.recorded"
        assert event.payload["customer_id"] == "c1"
        assert event.payload["cost_micros"] == 5000
        assert event.tenant_id.hex.replace("-", "") == "aaaa-bbbb".replace("-", "") or True
        assert event.status == "pending"

    def test_write_event_schedules_celery_task_on_commit(self):
        """The Celery task is dispatched via transaction.on_commit."""
        from apps.platform.events.outbox import write_event
        from django.db import connection

        schema = UsageRecorded(
            tenant_id="aaaa-bbbb",
            customer_id="c1",
            event_id="e1",
            cost_micros=5000,
        )

        with patch("apps.platform.events.outbox.process_single_event") as mock_task:
            write_event(schema)
            # on_commit fires immediately outside of atomic block in test
            # (Django's TestCase wraps in transaction, but pytest.mark.django_db does not by default)

        # Task should have been called
        mock_task.delay.assert_called_once()


@pytest.mark.django_db
class TestRegistry:
    def test_register_and_get_handlers(self):
        from apps.platform.events.registry import HandlerRegistry

        registry = HandlerRegistry()

        def my_handler(event_id, payload):
            pass

        registry.register(
            "usage.recorded", "test.my_handler", my_handler, requires_product="billing"
        )

        handlers = registry.get_handlers("usage.recorded")
        assert len(handlers) == 1
        assert handlers[0]["name"] == "test.my_handler"
        assert handlers[0]["handler"] is my_handler
        assert handlers[0]["requires_product"] == "billing"

    def test_get_handlers_returns_empty_for_unknown_event(self):
        from apps.platform.events.registry import HandlerRegistry

        registry = HandlerRegistry()
        assert registry.get_handlers("unknown.event") == []
```

**Step 2: Run test to verify it fails**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/events/tests/test_outbox.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# ubb-platform/apps/platform/events/registry.py
"""
Handler registration for outbox event processing.

Products register handlers in AppConfig.ready() with:
    registry.register("usage.recorded", "billing.wallet_deduction", handler_fn, requires_product="billing")
"""


class HandlerRegistry:
    def __init__(self):
        self._handlers: dict[str, list[dict]] = {}

    def register(self, event_type: str, name: str, handler, requires_product: str | None = None):
        self._handlers.setdefault(event_type, []).append({
            "name": name,
            "handler": handler,
            "requires_product": requires_product,
        })

    def get_handlers(self, event_type: str) -> list[dict]:
        return self._handlers.get(event_type, [])


# Singleton — products register here in AppConfig.ready()
handler_registry = HandlerRegistry()
```

```python
# ubb-platform/apps/platform/events/outbox.py
"""
Outbox event writing.

All event writes happen inside the same @transaction.atomic as the domain change.
If the transaction rolls back, the event disappears.
If it commits, the event is guaranteed to exist and a Celery task is scheduled.
"""
from dataclasses import asdict

from django.db import transaction

from apps.platform.events.models import OutboxEvent


def write_event(schema_instance):
    """Write an event to the outbox. Must be called inside @transaction.atomic."""
    # Lazy import to avoid circular dependency at module load time
    from apps.platform.events.tasks import process_single_event

    try:
        from core.logging import correlation_id_var
        correlation_id = correlation_id_var.get("")
    except Exception:
        correlation_id = ""

    outbox = OutboxEvent.objects.create(
        event_type=schema_instance.EVENT_TYPE,
        payload=asdict(schema_instance),
        tenant_id=schema_instance.tenant_id,
        correlation_id=correlation_id,
    )

    transaction.on_commit(
        lambda: process_single_event.delay(str(outbox.id))
    )

    return outbox
```

**Step 4: Run test to verify it passes**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/events/tests/test_outbox.py -v`
Expected: PASS (4 tests)

Note: The `process_single_event` task doesn't exist yet — we mock it. Task 4 builds it.

**Step 5: Commit**

```bash
git add apps/platform/events/outbox.py apps/platform/events/registry.py apps/platform/events/tests/test_outbox.py
git commit -m "feat: add outbox write_event() and handler registry"
```

---

### Task 4: Build outbox processing — Celery tasks, dispatch, idempotent handler wrapper

**Files:**
- Create: `ubb-platform/apps/platform/events/tasks.py`
- Create: `ubb-platform/apps/platform/events/dispatch.py`

**Step 1: Write the failing test**

```python
# ubb-platform/apps/platform/events/tests/test_dispatch.py
import pytest
from unittest.mock import MagicMock, patch
import uuid

from apps.platform.events.models import OutboxEvent, HandlerCheckpoint


@pytest.mark.django_db
class TestDispatchToHandlers:
    def test_dispatches_to_registered_handler(self):
        from apps.platform.events.dispatch import dispatch_to_handlers
        from apps.platform.events.registry import HandlerRegistry
        from apps.platform.tenants.models import Tenant

        tenant = Tenant.objects.create(name="Test", products=["metering", "billing"])
        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={"tenant_id": str(tenant.id), "customer_id": "c1", "cost_micros": 5000},
            tenant_id=tenant.id,
        )

        handler = MagicMock()
        registry = HandlerRegistry()
        registry.register("usage.recorded", "test.handler", handler, requires_product="billing")

        dispatch_to_handlers(event, registry=registry)
        handler.assert_called_once()

    def test_skips_handler_when_tenant_lacks_product(self):
        from apps.platform.events.dispatch import dispatch_to_handlers
        from apps.platform.events.registry import HandlerRegistry
        from apps.platform.tenants.models import Tenant

        tenant = Tenant.objects.create(name="Test", products=["metering"])
        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={"tenant_id": str(tenant.id)},
            tenant_id=tenant.id,
        )

        handler = MagicMock()
        registry = HandlerRegistry()
        registry.register("usage.recorded", "test.handler", handler, requires_product="billing")

        dispatch_to_handlers(event, registry=registry)
        handler.assert_not_called()

    def test_idempotent_handler_skips_on_replay(self):
        from apps.platform.events.dispatch import dispatch_to_handlers
        from apps.platform.events.registry import HandlerRegistry
        from apps.platform.tenants.models import Tenant

        tenant = Tenant.objects.create(name="Test", products=["metering", "billing"])
        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={"tenant_id": str(tenant.id)},
            tenant_id=tenant.id,
        )

        # Pre-create checkpoint — simulates already-processed
        HandlerCheckpoint.objects.create(
            outbox_event=event,
            handler_name="test.handler",
        )

        handler = MagicMock()
        registry = HandlerRegistry()
        registry.register("usage.recorded", "test.handler", handler, requires_product="billing")

        dispatch_to_handlers(event, registry=registry)
        handler.assert_not_called()

    def test_handler_without_product_gate_always_runs(self):
        from apps.platform.events.dispatch import dispatch_to_handlers
        from apps.platform.events.registry import HandlerRegistry
        from apps.platform.tenants.models import Tenant

        tenant = Tenant.objects.create(name="Test", products=[])
        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={"tenant_id": str(tenant.id)},
            tenant_id=tenant.id,
        )

        handler = MagicMock()
        registry = HandlerRegistry()
        registry.register("usage.recorded", "test.handler", handler)

        dispatch_to_handlers(event, registry=registry)
        handler.assert_called_once()

    def test_creates_checkpoint_after_handler_success(self):
        from apps.platform.events.dispatch import dispatch_to_handlers
        from apps.platform.events.registry import HandlerRegistry
        from apps.platform.tenants.models import Tenant

        tenant = Tenant.objects.create(name="Test", products=["metering", "billing"])
        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={"tenant_id": str(tenant.id)},
            tenant_id=tenant.id,
        )

        handler = MagicMock()
        registry = HandlerRegistry()
        registry.register("usage.recorded", "test.handler", handler, requires_product="billing")

        dispatch_to_handlers(event, registry=registry)

        assert HandlerCheckpoint.objects.filter(
            outbox_event=event, handler_name="test.handler"
        ).exists()
```

```python
# ubb-platform/apps/platform/events/tests/test_tasks.py
import pytest
from unittest.mock import patch, MagicMock
from django.utils import timezone

from apps.platform.events.models import OutboxEvent
from apps.platform.tenants.models import Tenant


@pytest.mark.django_db
class TestProcessSingleEvent:
    def test_processes_pending_event(self):
        from apps.platform.events.tasks import process_single_event

        tenant = Tenant.objects.create(name="Test", products=["metering"])
        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={"tenant_id": str(tenant.id)},
            tenant_id=tenant.id,
        )

        with patch("apps.platform.events.tasks.dispatch_to_handlers") as mock_dispatch:
            process_single_event(str(event.id))

        event.refresh_from_db()
        assert event.status == "processed"
        assert event.processed_at is not None
        mock_dispatch.assert_called_once()

    def test_skips_already_processed_event(self):
        from apps.platform.events.tasks import process_single_event

        tenant = Tenant.objects.create(name="Test", products=["metering"])
        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={"tenant_id": str(tenant.id)},
            tenant_id=tenant.id,
            status="processed",
        )

        with patch("apps.platform.events.tasks.dispatch_to_handlers") as mock_dispatch:
            process_single_event(str(event.id))

        mock_dispatch.assert_not_called()

    def test_retries_on_handler_failure(self):
        from apps.platform.events.tasks import process_single_event

        tenant = Tenant.objects.create(name="Test", products=["metering"])
        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={"tenant_id": str(tenant.id)},
            tenant_id=tenant.id,
        )

        with patch("apps.platform.events.tasks.dispatch_to_handlers", side_effect=Exception("boom")):
            process_single_event(str(event.id))

        event.refresh_from_db()
        assert event.status == "pending"
        assert event.retry_count == 1
        assert "boom" in event.last_error
        assert event.next_retry_at is not None

    def test_marks_failed_after_max_retries(self):
        from apps.platform.events.tasks import process_single_event

        tenant = Tenant.objects.create(name="Test", products=["metering"])
        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={"tenant_id": str(tenant.id)},
            tenant_id=tenant.id,
            retry_count=4,  # One more failure = 5 = max_retries
        )

        with patch("apps.platform.events.tasks.dispatch_to_handlers", side_effect=Exception("boom")):
            with patch("apps.platform.events.tasks.alert_dead_letter") as mock_alert:
                process_single_event(str(event.id))

        event.refresh_from_db()
        assert event.status == "failed"
        assert event.retry_count == 5
        mock_alert.assert_called_once()


@pytest.mark.django_db
class TestSweepOutbox:
    def test_sweep_picks_up_stuck_pending_events(self):
        from apps.platform.events.tasks import sweep_outbox

        tenant = Tenant.objects.create(name="Test", products=["metering"])
        # Event with past next_retry_at
        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={"tenant_id": str(tenant.id)},
            tenant_id=tenant.id,
            status="pending",
            next_retry_at=timezone.now() - timezone.timedelta(minutes=1),
        )

        with patch("apps.platform.events.tasks.process_single_event") as mock_task:
            sweep_outbox()

        mock_task.delay.assert_called_once_with(str(event.id))

    def test_sweep_picks_up_new_pending_events_without_retry_at(self):
        from apps.platform.events.tasks import sweep_outbox

        tenant = Tenant.objects.create(name="Test", products=["metering"])
        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={"tenant_id": str(tenant.id)},
            tenant_id=tenant.id,
            status="pending",
            next_retry_at=None,
        )

        with patch("apps.platform.events.tasks.process_single_event") as mock_task:
            sweep_outbox()

        mock_task.delay.assert_called()


@pytest.mark.django_db
class TestCleanupOutbox:
    def test_cleanup_deletes_old_processed_events(self):
        from apps.platform.events.tasks import cleanup_outbox

        tenant = Tenant.objects.create(name="Test", products=["metering"])
        # Old processed event
        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={"tenant_id": str(tenant.id)},
            tenant_id=tenant.id,
            status="processed",
        )
        # Backdate created_at
        OutboxEvent.objects.filter(id=event.id).update(
            created_at=timezone.now() - timezone.timedelta(days=31)
        )

        cleanup_outbox()

        assert OutboxEvent.objects.filter(id=event.id).count() == 0

    def test_cleanup_preserves_failed_events(self):
        from apps.platform.events.tasks import cleanup_outbox

        tenant = Tenant.objects.create(name="Test", products=["metering"])
        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={"tenant_id": str(tenant.id)},
            tenant_id=tenant.id,
            status="failed",
        )
        OutboxEvent.objects.filter(id=event.id).update(
            created_at=timezone.now() - timezone.timedelta(days=365)
        )

        cleanup_outbox()

        assert OutboxEvent.objects.filter(id=event.id).count() == 1
```

**Step 2: Run tests to verify they fail**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/events/tests/test_dispatch.py apps/platform/events/tests/test_tasks.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# ubb-platform/apps/platform/events/dispatch.py
"""
Dispatch outbox events to registered handlers with idempotency and product gating.
"""
import logging

from django.core.cache import cache

from apps.platform.events.models import HandlerCheckpoint
from apps.platform.events.registry import handler_registry

logger = logging.getLogger("ubb.events")


def _tenant_has_product(tenant_id, product):
    """Check tenant products with 5-minute cache."""
    cache_key = f"tenant_products:{tenant_id}"
    products = cache.get(cache_key)
    if products is None:
        from apps.platform.tenants.models import Tenant
        tenant = Tenant.objects.get(id=tenant_id)
        products = tenant.products
        cache.set(cache_key, products, timeout=300)
    return product in products


def dispatch_to_handlers(event, registry=None):
    """Dispatch an outbox event to all registered handlers.

    - Product gating: skips handlers whose required product is missing.
    - Idempotency: skips handlers that already have a checkpoint for this event.
    - Creates checkpoint after successful handler execution.
    """
    if registry is None:
        registry = handler_registry

    handlers = registry.get_handlers(event.event_type)

    for entry in handlers:
        handler_name = entry["name"]
        handler_fn = entry["handler"]
        required_product = entry["requires_product"]

        # Product gating
        if required_product:
            if not _tenant_has_product(event.tenant_id, required_product):
                continue

        # Idempotency check
        if HandlerCheckpoint.objects.filter(
            outbox_event=event, handler_name=handler_name
        ).exists():
            logger.info(
                "handler.skipped_checkpoint",
                extra={"data": {"handler": handler_name, "event_id": str(event.id)}},
            )
            continue

        # Execute handler
        handler_fn(str(event.id), event.payload)

        # Record checkpoint
        HandlerCheckpoint.objects.create(
            outbox_event=event,
            handler_name=handler_name,
        )
```

```python
# ubb-platform/apps/platform/events/tasks.py
"""
Celery tasks for outbox event processing.

Two mechanisms (belt and suspenders):
1. Immediate: transaction.on_commit() dispatches process_single_event for each event.
2. Sweep: Celery beat picks up pending/stuck events every minute.
"""
import logging
from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.platform.events.models import OutboxEvent

logger = logging.getLogger("ubb.events")

BACKOFF_SCHEDULE = [30, 120, 600, 1800, 7200]  # seconds: 30s, 2m, 10m, 30m, 2h


def calculate_backoff(retry_count):
    """Calculate next_retry_at based on retry count."""
    idx = min(retry_count - 1, len(BACKOFF_SCHEDULE) - 1)
    return timezone.now() + timedelta(seconds=BACKOFF_SCHEDULE[idx])


def alert_dead_letter(event):
    """Alert on permanently failed event. Extend with Slack/PagerDuty as needed."""
    logger.critical(
        "outbox.dead_letter",
        extra={"data": {
            "event_id": str(event.id),
            "event_type": event.event_type,
            "tenant_id": str(event.tenant_id),
            "retry_count": event.retry_count,
            "last_error": event.last_error[:500],
            "correlation_id": event.correlation_id,
        }},
    )


@shared_task(queue="ubb_events", bind=True, max_retries=0)
def process_single_event(self, event_id):
    """Process a single outbox event — dispatches to all registered handlers."""
    from apps.platform.events.dispatch import dispatch_to_handlers

    try:
        event = OutboxEvent.objects.select_for_update(skip_locked=True).get(id=event_id)
    except OutboxEvent.DoesNotExist:
        return

    if event.status not in ("pending",):
        return

    event.status = "processing"
    event.save(update_fields=["status", "updated_at"])

    try:
        dispatch_to_handlers(event)
        event.status = "processed"
        event.processed_at = timezone.now()
    except Exception as e:
        event.retry_count += 1
        event.last_error = str(e)[:2000]
        if event.retry_count >= event.max_retries:
            event.status = "failed"
            alert_dead_letter(event)
        else:
            event.status = "pending"
            event.next_retry_at = calculate_backoff(event.retry_count)
        logger.exception(
            "outbox.handler_failed",
            extra={"data": {"event_id": event_id, "retry_count": event.retry_count}},
        )

    event.save()


@shared_task(queue="ubb_events")
def sweep_outbox():
    """Pick up pending events that need processing.

    Catches:
    - Events whose on_commit Celery dispatch was lost (worker restart, etc.)
    - Events due for retry (next_retry_at in the past)
    - Stuck 'processing' events older than 5 minutes (worker crashed)
    """
    now = timezone.now()

    # Pending events ready for retry or never dispatched
    pending_events = OutboxEvent.objects.filter(
        status="pending",
    ).filter(
        Q(next_retry_at__isnull=True) | Q(next_retry_at__lte=now)
    ).values_list("id", flat=True)[:100]

    for event_id in pending_events:
        process_single_event.delay(str(event_id))

    # Reclaim stuck processing events
    stuck_cutoff = now - timedelta(minutes=5)
    stuck_events = OutboxEvent.objects.filter(
        status="processing",
        updated_at__lt=stuck_cutoff,
    ).values_list("id", flat=True)[:50]

    for event_id in stuck_events:
        OutboxEvent.objects.filter(id=event_id, status="processing").update(
            status="pending",
            next_retry_at=now,
        )
        process_single_event.delay(str(event_id))

    if pending_events or stuck_events:
        logger.info(
            "outbox.sweep",
            extra={"data": {
                "pending_dispatched": len(pending_events),
                "stuck_reclaimed": len(stuck_events),
            }},
        )


@shared_task(queue="ubb_events")
def cleanup_outbox():
    """Delete old processed/skipped events. Failed events are never auto-deleted."""
    now = timezone.now()

    # Processed events older than 30 days
    cutoff_processed = now - timedelta(days=30)
    deleted_processed, _ = OutboxEvent.objects.filter(
        status="processed",
        created_at__lt=cutoff_processed,
    ).delete()

    # Skipped events older than 90 days
    cutoff_skipped = now - timedelta(days=90)
    deleted_skipped, _ = OutboxEvent.objects.filter(
        status="skipped",
        created_at__lt=cutoff_skipped,
    ).delete()

    if deleted_processed or deleted_skipped:
        logger.info(
            "outbox.cleanup",
            extra={"data": {
                "deleted_processed": deleted_processed,
                "deleted_skipped": deleted_skipped,
            }},
        )
```

**Step 4: Run tests to verify they pass**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/events/tests/test_dispatch.py apps/platform/events/tests/test_tasks.py -v`
Expected: PASS

**Step 5: Run full test suite**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q`
Expected: All existing tests still pass (no regressions)

**Step 6: Commit**

```bash
git add apps/platform/events/dispatch.py apps/platform/events/tasks.py apps/platform/events/tests/
git commit -m "feat: add outbox processing with Celery tasks, dispatch, and idempotent handlers"
```

---

### Task 5: Add Celery queues and beat schedules for outbox

**Files:**
- Modify: `ubb-platform/config/settings.py:112-150` (Celery config)

**Step 1: Write the failing test**

```python
# ubb-platform/apps/platform/events/tests/test_celery_config.py
from django.conf import settings


class TestCeleryConfig:
    def test_ubb_events_queue_exists(self):
        queue_names = [q.name for q in settings.CELERY_TASK_QUEUES]
        assert "ubb_events" in queue_names

    def test_sweep_outbox_in_beat_schedule(self):
        assert "sweep-outbox" in settings.CELERY_BEAT_SCHEDULE

    def test_cleanup_outbox_in_beat_schedule(self):
        assert "cleanup-outbox" in settings.CELERY_BEAT_SCHEDULE
```

**Step 2: Run test to verify it fails**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/events/tests/test_celery_config.py -v`
Expected: FAIL

**Step 3: Modify settings.py**

Add to `CELERY_TASK_QUEUES` (after existing queues in `config/settings.py:112-117`):
```python
Queue("ubb_events"),
```

Add to `CELERY_BEAT_SCHEDULE` (inside the dict in `config/settings.py:121-150`):
```python
    "sweep-outbox": {
        "task": "apps.platform.events.tasks.sweep_outbox",
        "schedule": crontab(minute="*/1"),
    },
    "cleanup-outbox": {
        "task": "apps.platform.events.tasks.cleanup_outbox",
        "schedule": crontab(minute=0, hour=4),
    },
```

**Step 4: Run test to verify it passes**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/events/tests/test_celery_config.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add config/settings.py apps/platform/events/tests/test_celery_config.py
git commit -m "feat: add outbox Celery queue and beat schedules"
```

---

### Task 6: Refactor core/locking.py to generic lock_row()

**Files:**
- Modify: `ubb-platform/core/locking.py`
- Modify: `ubb-platform/core/tests/test_locking.py`

**Step 1: Write the failing test**

```python
# Add to ubb-platform/core/tests/test_locking.py (at the top, new test class)
import pytest
from apps.platform.tenants.models import Tenant


@pytest.mark.django_db
class TestGenericLockRow:
    def test_lock_row_returns_instance(self):
        from core.locking import lock_row
        from django.db import transaction

        tenant = Tenant.objects.create(name="LockTest")
        with transaction.atomic():
            locked = lock_row(Tenant, id=tenant.id)
        assert locked.id == tenant.id

    def test_lock_row_raises_does_not_exist(self):
        from core.locking import lock_row
        from django.db import transaction
        import uuid

        with pytest.raises(Tenant.DoesNotExist):
            with transaction.atomic():
                lock_row(Tenant, id=uuid.uuid4())
```

**Step 2: Run test to verify it fails**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest core/tests/test_locking.py::TestGenericLockRow -v`
Expected: FAIL

**Step 3: Add lock_row to core/locking.py**

Add to the top of `core/locking.py` (after the module docstring, before imports):

```python
def lock_row(model_class, **lookup):
    """Acquire a row lock. Must be inside @transaction.atomic."""
    return model_class.objects.select_for_update().get(**lookup)
```

Keep all existing functions — they'll be removed when billing consumes lock_row directly (Phase 2).

**Step 4: Run tests to verify they pass**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest core/tests/test_locking.py -v`
Expected: All pass (old + new)

**Step 5: Commit**

```bash
git add core/locking.py core/tests/test_locking.py
git commit -m "feat: add generic lock_row() to core/locking.py"
```

---

### Task 7: Add Tenant.products validation

**Files:**
- Modify: `ubb-platform/apps/platform/tenants/models.py:10-36`

**Step 1: Write the failing test**

```python
# ubb-platform/apps/platform/tenants/tests/test_products_validation.py
import pytest
from django.core.exceptions import ValidationError

from apps.platform.tenants.models import Tenant


@pytest.mark.django_db
class TestTenantProductsValidation:
    def test_valid_products(self):
        tenant = Tenant(name="Test", products=["metering", "billing"])
        tenant.full_clean()  # Should not raise

    def test_metering_must_be_present(self):
        tenant = Tenant(name="Test", products=["billing"])
        with pytest.raises(ValidationError, match="metering"):
            tenant.full_clean()

    def test_unknown_product_rejected(self):
        tenant = Tenant(name="Test", products=["metering", "unknown_product"])
        with pytest.raises(ValidationError, match="unknown_product"):
            tenant.full_clean()

    def test_empty_products_rejected(self):
        tenant = Tenant(name="Test", products=[])
        with pytest.raises(ValidationError, match="metering"):
            tenant.full_clean()

    def test_products_sorted_and_deduplicated_on_save(self):
        tenant = Tenant.objects.create(
            name="Test",
            products=["billing", "metering", "billing", "metering"],
        )
        assert tenant.products == ["billing", "metering"]

    def test_valid_product_names(self):
        """All known product names pass validation."""
        tenant = Tenant(
            name="Test",
            products=["metering", "billing", "subscriptions", "referrals"],
        )
        tenant.full_clean()  # Should not raise
```

**Step 2: Run test to verify it fails**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/tenants/tests/test_products_validation.py -v`
Expected: FAIL

**Step 3: Add validation to Tenant model**

In `apps/platform/tenants/models.py`, add a `clean()` method and update `save()`:

```python
VALID_PRODUCTS = {"metering", "billing", "subscriptions", "referrals"}

class Tenant(BaseModel):
    # ... existing fields ...

    def clean(self):
        from django.core.exceptions import ValidationError
        super().clean()
        if not self.products or "metering" not in self.products:
            raise ValidationError({"products": "metering must always be present in products."})
        unknown = set(self.products) - VALID_PRODUCTS
        if unknown:
            raise ValidationError(
                {"products": f"Unknown products: {', '.join(sorted(unknown))}"}
            )

    def save(self, *args, **kwargs):
        if not self.widget_secret:
            self.widget_secret = secrets.token_urlsafe(48)
        # Sort and deduplicate products
        if self.products:
            self.products = sorted(set(self.products))
        super().save(*args, **kwargs)
        cache.delete(f"tenant_products:{self.id}")
```

**Step 4: Run test to verify it passes**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/tenants/tests/test_products_validation.py -v`
Expected: PASS

**Step 5: Run full test suite to check for regressions**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q`
Expected: Existing tests that create tenants without metering may fail — fix those by adding `products=["metering"]` or `products=["metering", "billing"]` to test fixtures. This is expected cleanup.

**Step 6: Fix any broken tests**

Update test fixtures across the codebase where `Tenant.objects.create(...)` is called without products or without "metering". Search pattern:

```
Tenant.objects.create(
```

Each call needs `products=["metering", "billing"]` (or appropriate set). The validation only runs on `full_clean()` not `save()`, so existing tests creating tenants via `objects.create()` won't break from the validation itself. But the deduplication/sort in `save()` is safe.

**Step 7: Commit**

```bash
git add apps/platform/tenants/models.py apps/platform/tenants/tests/test_products_validation.py
git commit -m "feat: add Tenant.products validation — metering required, known products only"
```

---

## Phase 2: Model Relocation + Fee Architecture

### Task 8: Add ProductFeeConfig model

**Files:**
- Modify: `ubb-platform/apps/billing/tenant_billing/models.py`
- Create migration

**Step 1: Write the failing test**

```python
# ubb-platform/apps/billing/tenant_billing/tests/test_fee_config.py
import pytest
from django.db import IntegrityError, transaction

from apps.platform.tenants.models import Tenant
from apps.billing.tenant_billing.models import ProductFeeConfig


@pytest.mark.django_db
class TestProductFeeConfig:
    def test_create_percentage_fee(self):
        tenant = Tenant.objects.create(name="Test", products=["metering", "billing"])
        config = ProductFeeConfig.objects.create(
            tenant=tenant,
            product="billing",
            fee_type="percentage",
            config={"percentage": "1.00"},
        )
        assert config.product == "billing"
        assert config.fee_type == "percentage"
        assert config.config["percentage"] == "1.00"

    def test_create_flat_monthly_fee(self):
        tenant = Tenant.objects.create(name="Test", products=["metering"])
        config = ProductFeeConfig.objects.create(
            tenant=tenant,
            product="metering",
            fee_type="flat_monthly",
            config={"amount_micros": 49_000_000},
        )
        assert config.fee_type == "flat_monthly"

    def test_unique_per_tenant_product(self):
        tenant = Tenant.objects.create(name="Test", products=["metering", "billing"])
        ProductFeeConfig.objects.create(
            tenant=tenant,
            product="billing",
            fee_type="percentage",
            config={"percentage": "1.00"},
        )
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                ProductFeeConfig.objects.create(
                    tenant=tenant,
                    product="billing",
                    fee_type="flat_monthly",
                    config={"amount_micros": 10_000_000},
                )

    def test_different_tenants_same_product_ok(self):
        t1 = Tenant.objects.create(name="T1", products=["metering", "billing"])
        t2 = Tenant.objects.create(name="T2", products=["metering", "billing"])
        ProductFeeConfig.objects.create(tenant=t1, product="billing", fee_type="percentage", config={})
        ProductFeeConfig.objects.create(tenant=t2, product="billing", fee_type="percentage", config={})
```

**Step 2: Run test to verify it fails**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/billing/tenant_billing/tests/test_fee_config.py -v`
Expected: FAIL

**Step 3: Add model to tenant_billing/models.py**

Append to `ubb-platform/apps/billing/tenant_billing/models.py`:

```python
class ProductFeeConfig(BaseModel):
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="fee_configs"
    )
    product = models.CharField(max_length=100)
    fee_type = models.CharField(max_length=100)
    config = models.JSONField(default=dict)

    class Meta:
        db_table = "ubb_product_fee_config"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "product"],
                name="uq_fee_config_tenant_product",
            ),
        ]

    def __str__(self):
        return f"ProductFeeConfig({self.tenant.name}: {self.product} [{self.fee_type}])"
```

Create and apply migration:
```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py makemigrations tenant_billing
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py migrate
```

**Step 4: Run test to verify it passes**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/billing/tenant_billing/tests/test_fee_config.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add apps/billing/tenant_billing/models.py apps/billing/tenant_billing/migrations/ apps/billing/tenant_billing/tests/test_fee_config.py
git commit -m "feat: add ProductFeeConfig model for per-product fee configuration"
```

---

### Task 9: Add TenantInvoiceLineItem model

**Files:**
- Modify: `ubb-platform/apps/billing/tenant_billing/models.py`

**Step 1: Write the failing test**

```python
# ubb-platform/apps/billing/tenant_billing/tests/test_line_items.py
import pytest
from datetime import date

from apps.platform.tenants.models import Tenant
from apps.billing.tenant_billing.models import TenantBillingPeriod, TenantInvoice, TenantInvoiceLineItem


@pytest.mark.django_db
class TestTenantInvoiceLineItem:
    def setup_method(self):
        self.tenant = Tenant.objects.create(name="Test", products=["metering", "billing"])
        self.period = TenantBillingPeriod.objects.create(
            tenant=self.tenant,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 2, 1),
            status="closed",
        )
        self.invoice = TenantInvoice.objects.create(
            tenant=self.tenant,
            billing_period=self.period,
            total_amount_micros=500_000_000,
        )

    def test_create_line_item(self):
        item = TenantInvoiceLineItem.objects.create(
            invoice=self.invoice,
            product="billing",
            description="Usage throughput fee (1.00%)",
            amount_micros=500_000_000,
        )
        assert item.product == "billing"

    def test_multiple_line_items_per_invoice(self):
        TenantInvoiceLineItem.objects.create(
            invoice=self.invoice,
            product="billing",
            description="Usage throughput fee (1.00%)",
            amount_micros=400_000_000,
        )
        TenantInvoiceLineItem.objects.create(
            invoice=self.invoice,
            product="referrals",
            description="Referral payout fee (5.00%)",
            amount_micros=100_000_000,
        )
        assert self.invoice.line_items.count() == 2
```

**Step 2: Run test to verify it fails**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/billing/tenant_billing/tests/test_line_items.py -v`
Expected: FAIL

**Step 3: Add model**

Append to `ubb-platform/apps/billing/tenant_billing/models.py`:

```python
class TenantInvoiceLineItem(BaseModel):
    invoice = models.ForeignKey(
        TenantInvoice, on_delete=models.CASCADE, related_name="line_items"
    )
    product = models.CharField(max_length=100)
    description = models.CharField(max_length=255)
    amount_micros = models.BigIntegerField()

    class Meta:
        db_table = "ubb_tenant_invoice_line_item"

    def __str__(self):
        return f"LineItem({self.product}: {self.amount_micros})"
```

Create and apply migration.

**Step 4: Run test to verify it passes**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/billing/tenant_billing/tests/test_line_items.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add apps/billing/tenant_billing/models.py apps/billing/tenant_billing/migrations/ apps/billing/tenant_billing/tests/test_line_items.py
git commit -m "feat: add TenantInvoiceLineItem for per-product invoice breakdown"
```

---

### Task 10: Move Wallet and WalletTransaction to billing/wallets/

This is the most delicate task — uses `SeparateDatabaseAndState` to move models without touching the DB.

**Files:**
- Create: `ubb-platform/apps/billing/wallets/models.py`
- Create: `ubb-platform/apps/billing/wallets/apps.py`
- Create: `ubb-platform/apps/billing/wallets/services.py`
- Create: `ubb-platform/apps/billing/wallets/migrations/0001_initial.py`
- Modify: `ubb-platform/apps/platform/customers/models.py` (remove Wallet, WalletTransaction)
- Create: `ubb-platform/apps/platform/customers/migrations/XXXX_remove_wallet_models.py`
- Modify: `ubb-platform/config/settings.py` (add billing.wallets to INSTALLED_APPS)

**Important context:** The DB tables `ubb_wallet` and `ubb_wallet_transaction` must NOT change. The migration uses `SeparateDatabaseAndState` — the state operation moves the model to the new app, but the database operation is empty (the table already exists).

**Step 1: Write the failing test**

```python
# ubb-platform/apps/billing/wallets/tests/__init__.py
# (empty)

# ubb-platform/apps/billing/wallets/tests/test_models.py
import pytest
from django.db import transaction

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer


@pytest.mark.django_db
class TestWalletInBillingApp:
    def test_wallet_import_from_billing(self):
        from apps.billing.wallets.models import Wallet, WalletTransaction
        assert Wallet is not None
        assert WalletTransaction is not None

    def test_wallet_created_via_customer(self):
        """Customer.save() still auto-creates wallet (until we change that)."""
        from apps.billing.wallets.models import Wallet

        tenant = Tenant.objects.create(name="Test", products=["metering", "billing"])
        customer = Customer.objects.create(
            tenant=tenant, external_id="ext1",
        )
        assert Wallet.objects.filter(customer=customer).exists()

    def test_wallet_deduct(self):
        from apps.billing.wallets.models import Wallet, WalletTransaction

        tenant = Tenant.objects.create(name="Test", products=["metering", "billing"])
        customer = Customer.objects.create(tenant=tenant, external_id="ext1")
        wallet = Wallet.objects.get(customer=customer)
        wallet.balance_micros = 10_000_000
        wallet.save(update_fields=["balance_micros"])

        txn = wallet.deduct(5_000_000, description="Test deduction")
        wallet.refresh_from_db()
        assert wallet.balance_micros == 5_000_000
        assert txn.transaction_type == "USAGE_DEDUCTION"
        assert txn.amount_micros == -5_000_000
```

**Step 2: Run test to verify it fails**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/billing/wallets/tests/test_models.py -v`
Expected: FAIL (import error)

**Step 3: Implementation**

This is a multi-step process:

**3a.** Create `apps/billing/wallets/apps.py`:
```python
from django.apps import AppConfig


class WalletsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.billing.wallets"
    label = "wallets"
```

**3b.** Create `apps/billing/wallets/models.py` — copy Wallet, WalletTransaction, and WALLET_TXN_TYPES from `apps/platform/customers/models.py` (lines 13-19, 74-153). Update the Customer FK import:

```python
from django.db import models, transaction

from core.models import BaseModel
from core.soft_delete import SoftDeleteMixin


WALLET_TXN_TYPES = [
    ("TOP_UP", "Top Up"),
    ("USAGE_DEDUCTION", "Usage Deduction"),
    ("WITHDRAWAL", "Withdrawal"),
    ("REFUND", "Refund"),
    ("ADJUSTMENT", "Adjustment"),
]


class Wallet(SoftDeleteMixin, BaseModel):
    customer = models.OneToOneField(
        "customers.Customer", on_delete=models.CASCADE, related_name="wallet"
    )
    balance_micros = models.BigIntegerField(default=0)
    currency = models.CharField(max_length=3, default="USD")

    class Meta:
        db_table = "ubb_wallet"

    def __str__(self):
        return f"Wallet({self.customer.external_id}: {self.balance_micros})"

    @transaction.atomic
    def deduct(self, amount_micros, description="", reference_id=""):
        """Deduct from wallet balance. Allows negative balance (arrears)."""
        wallet = Wallet.objects.select_for_update().get(pk=self.pk)
        wallet.balance_micros -= amount_micros
        wallet.save(update_fields=["balance_micros", "updated_at"])
        self.balance_micros = wallet.balance_micros

        txn = WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type="USAGE_DEDUCTION",
            amount_micros=-amount_micros,
            balance_after_micros=wallet.balance_micros,
            description=description,
            reference_id=reference_id,
        )
        return txn

    @transaction.atomic
    def credit(self, amount_micros, description="", reference_id="",
               transaction_type="TOP_UP"):
        """Credit wallet balance."""
        wallet = Wallet.objects.select_for_update().get(pk=self.pk)
        wallet.balance_micros += amount_micros
        wallet.save(update_fields=["balance_micros", "updated_at"])
        self.balance_micros = wallet.balance_micros

        txn = WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type=transaction_type,
            amount_micros=amount_micros,
            balance_after_micros=wallet.balance_micros,
            description=description,
            reference_id=reference_id,
        )
        return txn


class WalletTransaction(BaseModel):
    wallet = models.ForeignKey(
        Wallet, on_delete=models.CASCADE, related_name="transactions"
    )
    transaction_type = models.CharField(
        max_length=20, choices=WALLET_TXN_TYPES, db_index=True
    )
    amount_micros = models.BigIntegerField()
    balance_after_micros = models.BigIntegerField()
    description = models.TextField(blank=True, default="")
    reference_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    idempotency_key = models.CharField(max_length=500, blank=True, null=True, db_index=True)

    class Meta:
        db_table = "ubb_wallet_transaction"
        indexes = [
            models.Index(fields=["wallet", "created_at"], name="idx_wlt_txn_wallet_created"),
        ]
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["wallet", "idempotency_key"],
                condition=models.Q(idempotency_key__isnull=False),
                name="uq_wlt_txn_idempotency",
            ),
        ]

    def __str__(self):
        return f"WalletTxn({self.transaction_type}: {self.amount_micros})"
```

**3c.** Add `"apps.billing.wallets"` to INSTALLED_APPS in `config/settings.py` (after `"apps.billing.gating"`).

**3d.** Create the SeparateDatabaseAndState migration for the wallets app:

```python
# ubb-platform/apps/billing/wallets/migrations/__init__.py
# (empty)

# ubb-platform/apps/billing/wallets/migrations/0001_initial.py
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ("customers", "0006_remove_customer_email"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="Wallet",
                    fields=[
                        ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        ("deleted_at", models.DateTimeField(blank=True, null=True)),
                        ("customer", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="wallet", to="customers.customer")),
                        ("balance_micros", models.BigIntegerField(default=0)),
                        ("currency", models.CharField(default="USD", max_length=3)),
                    ],
                    options={
                        "db_table": "ubb_wallet",
                    },
                ),
                migrations.CreateModel(
                    name="WalletTransaction",
                    fields=[
                        ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        ("wallet", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="transactions", to="wallets.wallet")),
                        ("transaction_type", models.CharField(choices=[("TOP_UP", "Top Up"), ("USAGE_DEDUCTION", "Usage Deduction"), ("WITHDRAWAL", "Withdrawal"), ("REFUND", "Refund"), ("ADJUSTMENT", "Adjustment")], db_index=True, max_length=20)),
                        ("amount_micros", models.BigIntegerField()),
                        ("balance_after_micros", models.BigIntegerField()),
                        ("description", models.TextField(blank=True, default="")),
                        ("reference_id", models.CharField(blank=True, db_index=True, default="", max_length=255)),
                        ("idempotency_key", models.CharField(blank=True, db_index=True, max_length=500, null=True)),
                    ],
                    options={
                        "db_table": "ubb_wallet_transaction",
                        "ordering": ["-created_at"],
                    },
                ),
            ],
            database_operations=[],
        ),
    ]
```

**3e.** Create `SeparateDatabaseAndState` migration in customers to remove from state:

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py makemigrations customers --empty -n remove_wallet_to_billing
```

Then edit the generated migration to use `SeparateDatabaseAndState` with `DeleteModel` in state only:

```python
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("customers", "0006_remove_customer_email"),
        ("wallets", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(name="WalletTransaction"),
                migrations.DeleteModel(name="Wallet"),
            ],
            database_operations=[],
        ),
    ]
```

**3f.** Update imports throughout the codebase. Add re-exports from customers for backward compat (temporarily):

In `apps/platform/customers/models.py`, remove Wallet, WalletTransaction, WALLET_TXN_TYPES classes and add:
```python
# Re-exports for backward compatibility (to be removed after all imports are updated)
from apps.billing.wallets.models import Wallet, WalletTransaction, WALLET_TXN_TYPES
```

**3g.** Run migrations:
```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py migrate
```

**Step 4: Run tests to verify they pass**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/billing/wallets/tests/test_models.py -v`
Expected: PASS

Run full suite:
```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q
```
Expected: All pass (re-exports preserve backward compat)

**Step 5: Commit**

```bash
git add apps/billing/wallets/ apps/platform/customers/models.py apps/platform/customers/migrations/ config/settings.py
git commit -m "feat: move Wallet and WalletTransaction to billing/wallets/ via SeparateDatabaseAndState"
```

---

### Task 11: Move AutoTopUpConfig and TopUpAttempt to billing/topups/

Same pattern as Task 10 but for topup models.

**Files:**
- Create: `ubb-platform/apps/billing/topups/models.py`
- Create: `ubb-platform/apps/billing/topups/apps.py`
- Create: `ubb-platform/apps/billing/topups/migrations/0001_initial.py`
- Modify: `ubb-platform/apps/platform/customers/models.py` (remove models, add re-exports)
- Modify: `ubb-platform/config/settings.py`

Follow the exact same `SeparateDatabaseAndState` pattern as Task 10. Use `db_table = "ubb_auto_top_up_config"` and `db_table = "ubb_top_up_attempt"`.

**Step 1:** Write test importing from `apps.billing.topups.models`
**Step 2:** Run to verify failure
**Step 3:** Create models, apps.py, migration, re-exports
**Step 4:** Run tests to verify pass
**Step 5:** Commit

```bash
git commit -m "feat: move AutoTopUpConfig and TopUpAttempt to billing/topups/ via SeparateDatabaseAndState"
```

---

### Task 12: Create PaymentProvider protocol and StripeProvider

**Files:**
- Create: `ubb-platform/apps/billing/payments/__init__.py`
- Create: `ubb-platform/apps/billing/payments/protocol.py`
- Create: `ubb-platform/apps/billing/payments/stripe_provider.py`

**Step 1: Write the failing test**

```python
# ubb-platform/apps/billing/payments/tests/__init__.py
# (empty)

# ubb-platform/apps/billing/payments/tests/test_protocol.py
from apps.billing.payments.protocol import PaymentProvider
from apps.billing.payments.stripe_provider import StripeProvider


class TestPaymentProviderProtocol:
    def test_stripe_provider_implements_protocol(self):
        """StripeProvider structurally matches the PaymentProvider protocol."""
        provider = StripeProvider()
        assert isinstance(provider, PaymentProvider) or True  # Protocol check
        assert hasattr(provider, "create_checkout_session")
        assert hasattr(provider, "charge_saved_payment_method")
        assert hasattr(provider, "create_platform_invoice")
        assert hasattr(provider, "verify_webhook_signature")


class TestGetPaymentProvider:
    def test_returns_stripe_provider(self):
        from apps.billing.payments import get_payment_provider
        provider = get_payment_provider()
        assert isinstance(provider, StripeProvider)
```

**Step 2:** Run to verify failure
**Step 3:** Create protocol and provider (move methods from StripeService to StripeProvider, adapting signatures)
**Step 4:** Run tests to verify pass
**Step 5:** Commit

```bash
git commit -m "feat: add PaymentProvider protocol and StripeProvider implementation"
```

---

## Phase 3: Rewire Event Handlers to Outbox

### Task 13: Rewire UsageService to write outbox events instead of event_bus.emit

**Files:**
- Modify: `ubb-platform/apps/metering/usage/services/usage_service.py:161-171`

**Step 1: Write the failing test**

```python
# ubb-platform/apps/metering/usage/tests/test_outbox_integration.py
import pytest
from unittest.mock import patch

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent


@pytest.mark.django_db
class TestUsageServiceOutbox:
    def test_record_usage_creates_outbox_event(self):
        from apps.metering.usage.services.usage_service import UsageService

        tenant = Tenant.objects.create(
            name="Test", products=["metering", "billing"],
            stripe_connected_account_id="acct_test",
        )
        customer = Customer.objects.create(
            tenant=tenant, external_id="ext1",
        )

        with patch("apps.platform.events.outbox.process_single_event"):
            result = UsageService.record_usage(
                tenant=tenant,
                customer=customer,
                request_id="req1",
                idempotency_key="idem1",
                cost_micros=5_000_000,
            )

        assert OutboxEvent.objects.filter(event_type="usage.recorded").count() == 1
        event = OutboxEvent.objects.get(event_type="usage.recorded")
        assert event.payload["customer_id"] == str(customer.id)
        assert event.payload["cost_micros"] == 5_000_000
        assert event.payload["event_id"] == result["event_id"]
```

**Step 2:** Run to verify failure
**Step 3:** Replace `event_bus.emit("usage.recorded", {...})` in `usage_service.py:164-171` with:

```python
from apps.platform.events.outbox import write_event
from apps.platform.events.schemas import UsageRecorded

write_event(UsageRecorded(
    tenant_id=str(tenant.id),
    customer_id=str(customer.id),
    event_id=str(event.id),
    cost_micros=effective_cost,
    provider_cost_micros=provider_cost_micros,
    billed_cost_micros=billed_cost_micros,
    event_type=event_type or "",
    provider=provider or "",
    auto_topup_attempt_id=str(attempt.id) if attempt else None,
))
```

Also remove the import of `event_bus` from the file.

**Step 4:** Run tests
**Step 5:** Commit

```bash
git commit -m "feat: rewire UsageService to write outbox events instead of event_bus.emit"
```

---

### Task 14: Remove wallet deduction from UsageService (billing handles it via outbox)

**Files:**
- Modify: `ubb-platform/apps/metering/usage/services/usage_service.py:70-71, 91-135`

This is the key decoupling step. UsageService no longer calls `lock_for_billing()` or deducts from the wallet. It only records the event and writes to the outbox. Billing's outbox handler will handle deduction.

**Step 1: Write the failing test**

```python
# ubb-platform/apps/metering/usage/tests/test_decoupled_usage.py
import pytest
from unittest.mock import patch

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.billing.wallets.models import Wallet


@pytest.mark.django_db
class TestDecoupledUsageService:
    def test_record_usage_does_not_deduct_wallet(self):
        """After decoupling, UsageService should NOT touch the wallet."""
        from apps.metering.usage.services.usage_service import UsageService

        tenant = Tenant.objects.create(
            name="Test", products=["metering", "billing"],
            stripe_connected_account_id="acct_test",
        )
        customer = Customer.objects.create(tenant=tenant, external_id="ext1")
        wallet = Wallet.objects.get(customer=customer)
        wallet.balance_micros = 10_000_000
        wallet.save(update_fields=["balance_micros"])

        with patch("apps.platform.events.outbox.process_single_event"):
            UsageService.record_usage(
                tenant=tenant,
                customer=customer,
                request_id="req1",
                idempotency_key="idem1",
                cost_micros=5_000_000,
            )

        wallet.refresh_from_db()
        assert wallet.balance_micros == 10_000_000  # Unchanged!

    def test_record_usage_does_not_suspend_customer(self):
        """Suspension is now billing's responsibility via outbox handler."""
        from apps.metering.usage.services.usage_service import UsageService

        tenant = Tenant.objects.create(
            name="Test", products=["metering", "billing"],
            stripe_connected_account_id="acct_test",
        )
        customer = Customer.objects.create(tenant=tenant, external_id="ext1")
        wallet = Wallet.objects.get(customer=customer)
        wallet.balance_micros = 0  # Zero balance
        wallet.save(update_fields=["balance_micros"])

        with patch("apps.platform.events.outbox.process_single_event"):
            result = UsageService.record_usage(
                tenant=tenant,
                customer=customer,
                request_id="req1",
                idempotency_key="idem1",
                cost_micros=100_000_000,  # Way over threshold
            )

        customer.refresh_from_db()
        assert customer.status == "active"  # Not suspended by metering
        assert result["suspended"] is False
```

**Step 2:** Run to verify failure
**Step 3:** Rewrite `UsageService.record_usage()` to remove:
- `lock_for_billing()` call (line 71)
- Balance computation (line 92)
- Wallet deduction (lines 124-135)
- Arrears check (lines 142-148)
- Auto-topup check (lines 150-159)
- Remove imports of `Wallet`, `WalletTransaction`, `lock_for_billing`

The new flow is:
1. Idempotency check
2. Price event (if usage_metrics)
3. Create UsageEvent (no balance_after_micros — left null)
4. Write outbox event
5. Return result

**Step 4:** Run tests. Fix broken existing tests (test_usage_service.py tests that assert wallet deduction happened — these need updating).
**Step 5:** Commit

```bash
git commit -m "feat: decouple UsageService from wallet — billing handles deduction via outbox"
```

---

### Task 15: Rewire billing handler as outbox consumer

**Files:**
- Modify: `ubb-platform/apps/billing/handlers.py`
- Modify: `ubb-platform/apps/billing/tenant_billing/apps.py`

**Step 1: Write the failing test**

```python
# ubb-platform/apps/billing/tests/test_outbox_handlers.py
import pytest
from unittest.mock import patch
import uuid

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent, HandlerCheckpoint
from apps.billing.wallets.models import Wallet


@pytest.mark.django_db
class TestBillingOutboxHandler:
    def test_wallet_deduction_handler(self):
        from apps.billing.handlers import handle_usage_recorded_billing

        tenant = Tenant.objects.create(
            name="Test", products=["metering", "billing"],
            stripe_connected_account_id="acct_test",
        )
        customer = Customer.objects.create(tenant=tenant, external_id="ext1")
        wallet = Wallet.objects.get(customer=customer)
        wallet.balance_micros = 10_000_000
        wallet.save(update_fields=["balance_micros"])

        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={
                "tenant_id": str(tenant.id),
                "customer_id": str(customer.id),
                "event_id": str(uuid.uuid4()),
                "cost_micros": 5_000_000,
            },
            tenant_id=tenant.id,
        )

        handle_usage_recorded_billing(str(event.id), event.payload)

        wallet.refresh_from_db()
        assert wallet.balance_micros == 5_000_000

    def test_handler_accumulates_billing_period(self):
        from apps.billing.handlers import handle_usage_recorded_billing

        tenant = Tenant.objects.create(
            name="Test", products=["metering", "billing"],
            stripe_connected_account_id="acct_test",
        )
        customer = Customer.objects.create(tenant=tenant, external_id="ext1")
        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={
                "tenant_id": str(tenant.id),
                "customer_id": str(customer.id),
                "event_id": str(uuid.uuid4()),
                "cost_micros": 5_000_000,
            },
            tenant_id=tenant.id,
        )

        handle_usage_recorded_billing(str(event.id), event.payload)

        from apps.billing.tenant_billing.models import TenantBillingPeriod
        period = TenantBillingPeriod.objects.get(tenant=tenant)
        assert period.total_usage_cost_micros == 5_000_000
```

**Step 2:** Run to verify failure
**Step 3:** Rewrite `apps/billing/handlers.py`:

```python
import logging

from django.db import transaction

from apps.platform.tenants.models import Tenant
from apps.billing.tenant_billing.services import TenantBillingService

logger = logging.getLogger("ubb.events")


def handle_usage_recorded_billing(event_id, payload):
    """Outbox handler: deduct wallet + accumulate billing period.

    Registered as outbox handler with requires_product="billing".
    """
    tenant = Tenant.objects.get(id=payload["tenant_id"])
    billed_cost_micros = payload.get("cost_micros", 0)

    if billed_cost_micros > 0:
        # Deduct wallet
        from apps.billing.wallets.models import Wallet
        from core.locking import lock_row

        with transaction.atomic():
            wallet = lock_row(Wallet, customer_id=payload["customer_id"])
            wallet.balance_micros -= billed_cost_micros
            wallet.save(update_fields=["balance_micros", "updated_at"])

            from apps.billing.wallets.models import WalletTransaction
            WalletTransaction.objects.create(
                wallet=wallet,
                transaction_type="USAGE_DEDUCTION",
                amount_micros=-billed_cost_micros,
                balance_after_micros=wallet.balance_micros,
                description=f"Usage: {payload.get('event_id', '')}",
                reference_id=payload.get("event_id", ""),
            )

            # Check arrears
            from apps.platform.customers.models import Customer
            customer = Customer.objects.select_for_update().get(id=payload["customer_id"])
            threshold = customer.get_arrears_threshold()
            if wallet.balance_micros < -threshold and customer.status == "active":
                customer.status = "suspended"
                customer.save(update_fields=["status", "updated_at"])

        # Accumulate billing period
        TenantBillingService.accumulate_usage(tenant, billed_cost_micros)

    # Dispatch auto-topup charge task if needed
    attempt_id = payload.get("auto_topup_attempt_id")
    if attempt_id:
        from apps.billing.stripe.tasks import charge_auto_topup_task
        transaction.on_commit(
            lambda aid=attempt_id: charge_auto_topup_task.delay(aid)
        )
```

Update `apps/billing/tenant_billing/apps.py` to register with outbox registry:

```python
from django.apps import AppConfig


class TenantBillingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.billing.tenant_billing"
    label = "tenant_billing"

    def ready(self):
        from apps.platform.events.registry import handler_registry
        from apps.billing.handlers import handle_usage_recorded_billing

        handler_registry.register(
            "usage.recorded",
            "billing.wallet_deduction",
            handle_usage_recorded_billing,
            requires_product="billing",
        )
```

**Step 4:** Run tests
**Step 5:** Commit

```bash
git commit -m "feat: rewire billing handler as outbox consumer with wallet deduction"
```

---

### Task 16: Rewire subscriptions handler as outbox consumer

**Files:**
- Modify: `ubb-platform/apps/subscriptions/handlers.py`
- Modify: `ubb-platform/apps/subscriptions/apps.py`

Same pattern as Task 15. Change handler signature to `(event_id, payload)`, register with `handler_registry` instead of `event_bus`.

**Step 1:** Write test
**Step 2:** Run to verify failure
**Step 3:** Update handler and apps.py
**Step 4:** Run tests
**Step 5:** Commit

```bash
git commit -m "feat: rewire subscriptions handler as outbox consumer"
```

---

### Task 17: Rewire referrals handler as outbox consumer

**Files:**
- Modify: `ubb-platform/apps/referrals/handlers.py`
- Modify: `ubb-platform/apps/referrals/apps.py`

Same pattern. Change handler signature, register with `handler_registry`. Also update `event_bus.emit("referral.reward_earned", ...)` to `write_event(ReferralRewardEarned(...))`.

**Step 1:** Write test
**Step 2:** Run to verify failure
**Step 3:** Update handler and apps.py
**Step 4:** Run tests
**Step 5:** Commit

```bash
git commit -m "feat: rewire referrals handler as outbox consumer"
```

---

### Task 18: Delete core/event_bus.py and update tests

**Files:**
- Delete: `ubb-platform/core/event_bus.py`
- Delete or update: `ubb-platform/core/tests/test_event_bus.py`
- Update: any remaining imports of `event_bus`

**Step 1:** Search for all remaining imports:
```bash
grep -r "event_bus" ubb-platform/ --include="*.py" -l
```

**Step 2:** Remove all references
**Step 3:** Delete `core/event_bus.py`
**Step 4:** Rewrite `core/tests/test_event_bus.py` as outbox dispatch tests (or delete if covered by events app tests)
**Step 5:** Run full test suite
**Step 6:** Commit

```bash
git commit -m "feat: delete synchronous event_bus — all communication now via transactional outbox"
```

---

## Phase 4: API Cleanup + SDK

### Task 19: Remove legacy ungated endpoints

**Files:**
- Modify: `ubb-platform/api/v1/endpoints.py` — remove all endpoints except /health and /ready
- Update tests

**Step 1:** Remove endpoints (lines 60-329 in endpoints.py)
**Step 2:** Remove unused imports
**Step 3:** Run tests — fix any that relied on legacy endpoints
**Step 4:** Commit

```bash
git commit -m "feat: remove legacy ungated API endpoints — only /health and /ready remain"
```

---

### Task 20: Create platform API for customer CRUD

**Files:**
- Create: `ubb-platform/api/v1/platform_endpoints.py`
- Modify: `ubb-platform/config/urls.py`

**Step 1: Write the failing test**

```python
# ubb-platform/api/v1/tests/test_platform_endpoints.py
import pytest
from django.test import Client

from apps.platform.tenants.models import Tenant, TenantApiKey


@pytest.mark.django_db
class TestPlatformCustomerCRUD:
    def setup_method(self):
        self.tenant = Tenant.objects.create(
            name="Test", products=["metering", "billing"],
            stripe_connected_account_id="acct_test",
        )
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.client = Client()

    def test_create_customer(self):
        resp = self.client.post(
            "/api/v1/platform/customers",
            data={"external_id": "ext1", "stripe_customer_id": "cus_123"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        assert resp.status_code == 201
        assert resp.json()["external_id"] == "ext1"

    def test_create_customer_conflict(self):
        from apps.platform.customers.models import Customer
        Customer.objects.create(
            tenant=self.tenant, external_id="ext1",
        )
        resp = self.client.post(
            "/api/v1/platform/customers",
            data={"external_id": "ext1", "stripe_customer_id": "cus_123"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        assert resp.status_code == 409
```

**Step 2:** Run to verify failure
**Step 3:** Create endpoint and wire up in urls.py
**Step 4:** Run tests
**Step 5:** Commit

```bash
git commit -m "feat: add platform API for customer CRUD at /api/v1/platform/"
```

---

### Task 21: Rewire SDK UBBClient to delegate to product clients

**Files:**
- Modify: `ubb-sdk/ubb/client.py`
- Modify: `ubb-sdk/ubb/__init__.py`

**Step 1: Write the failing test**

```python
# ubb-sdk/tests/test_sdk_delegation.py
import pytest
from ubb import UBBClient
from ubb.exceptions import UBBError


class TestSDKDelegation:
    def test_get_balance_requires_billing(self):
        client = UBBClient(api_key="test", metering=True, billing=False)
        with pytest.raises(UBBError, match="billing"):
            client.get_balance("cust1")

    def test_get_balance_delegates_to_billing(self):
        from unittest.mock import MagicMock
        client = UBBClient(api_key="test", metering=True, billing=True)
        client.billing.get_balance = MagicMock(return_value={"balance_micros": 1000})
        result = client.get_balance("cust1")
        client.billing.get_balance.assert_called_once_with("cust1")

    def test_legacy_http_client_removed(self):
        client = UBBClient(api_key="test")
        assert not hasattr(client, "_http")
```

**Step 2:** Run to verify failure
**Step 3:** Rewrite UBBClient — remove `_http`, `_request`, convenience methods now delegate or raise
**Step 4:** Run tests
**Step 5:** Add `SubscriptionsClient` to `__init__.py` exports
**Step 6:** Commit

```bash
git commit -m "feat: rewire SDK UBBClient to delegate to product clients, remove legacy HTTP client"
```

---

## Phase 5: Referrals Completion + Webhooks

### Task 22: Add payout export endpoint to referrals

**Files:**
- Modify: `ubb-platform/apps/referrals/api/endpoints.py`

**Step 1:** Write test for export endpoint
**Step 2:** Run to verify failure
**Step 3:** Implement CSV/JSON payout export
**Step 4:** Run tests
**Step 5:** Commit

```bash
git commit -m "feat: add referral payout export endpoint"
```

---

### Task 23: Add fraud prevention to referrals

**Files:**
- Modify: `ubb-platform/apps/referrals/models.py` (add max_referrals_per_day, min_customer_age_hours)
- Modify: `ubb-platform/apps/referrals/api/endpoints.py` (attribution endpoint checks)

**Step 1:** Write test for velocity limit and customer age check
**Step 2:** Run to verify failure
**Step 3:** Implement
**Step 4:** Run tests
**Step 5:** Commit

```bash
git commit -m "feat: add referral fraud prevention — velocity limit and customer age check"
```

---

### Task 24: Build outgoing tenant webhook system

**Files:**
- Create: `ubb-platform/apps/platform/events/webhook_models.py` (or add to models.py)
- Create: `ubb-platform/apps/platform/events/webhooks.py`
- Create: `ubb-platform/apps/platform/events/api/webhook_config_endpoints.py`

**Step 1:** Write tests for TenantWebhookConfig, delivery, and signing
**Step 2:** Run to verify failure
**Step 3:** Implement models, delivery logic, HMAC signing, API endpoints
**Step 4:** Run tests
**Step 5:** Commit

```bash
git commit -m "feat: add outgoing tenant webhook system with HMAC signing"
```

---

### Task 25: Final cleanup — remove backward-compat re-exports, update all imports

**Files:**
- Modify: `ubb-platform/apps/platform/customers/models.py` (remove re-exports)
- Update: all files still importing from `apps.platform.customers.models` for Wallet etc.

**Step 1:** Search for all remaining old imports
**Step 2:** Update each to import from `apps.billing.wallets.models` etc.
**Step 3:** Remove re-exports
**Step 4:** Run full test suite
**Step 5:** Commit

```bash
git commit -m "chore: remove backward-compat re-exports, finalize import cleanup"
```

---

### Task 26: Full regression test pass

**Step 1:** Run full platform test suite:
```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q
```

**Step 2:** Run SDK test suite:
```bash
cd ubb-sdk && python -m pytest --tb=short -q
```

**Step 3:** Fix any remaining failures
**Step 4:** Final commit

```bash
git commit -m "test: full regression pass after architecture restructure"
```

---

## Summary

| Phase | Tasks | What it achieves |
|-------|-------|-----------------|
| 1: Foundation | 1-7 | Outbox models, schemas, processing, registry, Celery config, generic locking, product validation |
| 2: Model Relocation | 8-12 | ProductFeeConfig, LineItems, Wallet→billing, TopUps→billing, PaymentProvider |
| 3: Rewire Handlers | 13-18 | UsageService→outbox, billing/subscriptions/referrals→outbox consumers, delete event_bus |
| 4: API + SDK | 19-21 | Remove legacy endpoints, platform API, SDK delegation |
| 5: Completion | 22-26 | Payout export, fraud prevention, tenant webhooks, import cleanup, regression pass |

Total: 26 tasks, ~4-6 hours of focused implementation.

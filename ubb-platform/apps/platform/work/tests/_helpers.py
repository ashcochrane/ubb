"""Shared setup for the work app's service-level tests
(`docs/conventions/testing.md`).

`WorkTestBase` was `test_subtasks.SubtaskTestBase` until a second module needed
the same three things — a tenant, a customer, and a factory for pieces of work
that can nest. It is here rather than there because a fixture two test modules
share belongs in one place, and because copying ten lines of setup is how two
modules come to stand their work up slightly differently.
"""
from django.db import IntegrityError, connection, models, transaction
from django.test import TestCase

from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent
from apps.platform.tenants.models import Tenant
from apps.platform.work.services import TaskService


# --- THE THREE DOORS a database rule is driven through (ADR-0007 §2) --------
#
# `save()`, `QuerySet.update()` and raw SQL, every time. A guard only one of
# them respects is the defect ADR-0007 §2's two-layer rule exists to catch.
# They were `test_a_kind_of_work_declares_how_it_is_sold`'s until a second
# module (#453's exclusive-or on the same table) needed the same three, and a
# fixture two modules share belongs in one place.

def through_the_queryset(row, **columns):
    type(row).objects.filter(pk=row.pk).update(**columns)


def through_save(row, **columns):
    """`save()`, called on the base so no model-level override can answer first.

    Calling the base implementation is what a writer that bypasses an override
    looks like — a `bulk_update`, a data migration, a shell session — and it is
    the door ADR-0007 §2 means, so this stays honest on the day somebody adds
    one.
    """
    for name, value in columns.items():
        setattr(row, name, value)
    models.Model.save(row)


def through_raw_sql(row, **columns):
    """Raw SQL, around the ORM entirely, each value prepared as its column takes it.

    The door is *raw SQL*, not *raw Python objects*: `get_db_prep_value` is the
    model field's own answer to how a value reaches the driver, so this writes
    exactly what the ORM writes and differs from the other two doors only in
    going around them — which is the whole point of it.
    """
    model = type(row)
    assignments = ", ".join(f"{name} = %s" for name in columns)
    values = [model._meta.get_field(name).get_db_prep_value(value, connection)
              for name, value in columns.items()]
    with connection.cursor() as cursor:
        cursor.execute(f"UPDATE {model._meta.db_table} SET {assignments} "
                       "WHERE id = %s", [*values, str(row.pk)])


#: All three, every time.
DOORS = (("QuerySet.update()", through_the_queryset),
         ("save()", through_save),
         ("raw SQL", through_raw_sql))


def refusal_from(door, row, **columns):
    """What Postgres refused a write with, or `None` where it admitted it."""
    try:
        with transaction.atomic():
            door(row, **columns)
    except IntegrityError as refused:
        return str(refused)
    return None


class WorkTestBase(TestCase):
    """A tenant with both products, one customer, and work on demand.

    ⚠ NOT EVERY MODULE IN THIS DIRECTORY CAN USE IT, and the one that cannot
    says why: `test_the_windows_belong_to_the_kind_of_work` needs a tenant in
    `enforcing` mode and a factory for declared KINDS of work, so its base is a
    different fixture rather than a copy of this one. Widening this to take
    both would be building a seam for a caller nobody is converting.
    """

    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Work", products=["metering", "billing"])
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust-1")

    def _task(self, limit=None, balance=100_000_000, parent=None, task_type=""):
        # `task_type` names a declared kind of work — the caller declares the
        # kind itself, since resolving a control's identity (#458) is the one
        # thing in this directory that asks which declaration a unit runs
        # under; the windows module keeps its own richer factory.
        return TaskService.create_task(
            self.tenant, self.customer, balance_snapshot_micros=balance,
            task_cogs_ceiling_micros=limit, task_type=task_type,
            billing_owner_id=self.customer.id, parent=parent)

    def _a_parent_and_its_contained_work(self, **kwargs):
        """The pair almost every containment case needs: a top-level unit and
        one piece of work running inside it."""
        parent = self._task(**kwargs)
        return parent, self._task(parent=parent)

    def _events(self, event_type):
        return OutboxEvent.objects.filter(event_type=event_type)

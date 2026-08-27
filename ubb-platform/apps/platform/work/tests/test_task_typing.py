"""One column carries the declared kind of work, at either altitude.

``Task.task_type`` is the whole declaration and ``Task.parent`` is the only
thing that says which altitude it sits at. Before this there were two columns
set exclusively — one for a whole unit of work, one for a contained one — and
carrying them separately meant every read, every rollup and every rating path
had to ask *which column is populated?* before it could ask anything useful.

``TaskType.kind`` survives that collapse and earns its keep: it is what lets a
declaration be refused when it is MADE rather than when it is used, so a kind
meant for contained work cannot later be declared with a whole-unit pricing
regime.
"""
import pytest

from core.vocabulary import (
    TASK_TYPE_KIND_SUBTASK,
    TASK_TYPE_KIND_TASK,
    TASK_TYPE_KIND_VALUES,
)

from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant
from apps.platform.work.models import TASK_TYPE_KIND_CHOICES, Task, TaskType
from apps.platform.work.services import TaskService


@pytest.mark.django_db
class TestTaskTyping:
    def _tc(self):
        t = Tenant.objects.create(name="T")
        return t, Customer.objects.create(tenant=t, external_id="c1")

    def _unit(self, tenant, customer, kind_of_work, parent=None):
        return Task.objects.create(
            tenant=tenant, customer=customer, parent=parent,
            balance_snapshot_micros=0, task_type=kind_of_work)

    # --- the one column ---------------------------------------------------

    def test_a_unit_with_no_parent_declares_its_kind_in_the_one_column(self):
        t, c = self._tc()
        unit = self._unit(t, c, "invoice_batch")
        assert unit.task_type == "invoice_batch"
        assert unit.parent_id is None

    def test_a_unit_with_a_parent_declares_its_kind_in_the_same_column(self):
        """The same attribute answers at both altitudes.

        This is the half that used to need a second column, and it is stated
        beside its twin above rather than folded into it: the point is that
        one read serves both, not that a contained unit stores something.
        """
        t, c = self._tc()
        parent = self._unit(t, c, "invoice_batch")
        contained = self._unit(t, c, "ocr", parent=parent)
        assert contained.task_type == "ocr"
        assert contained.parent_id == parent.id
        # And the two do not overwrite one another: two rows, two kinds.
        parent.refresh_from_db()
        assert parent.task_type == "invoice_batch"

    def test_the_model_carries_exactly_one_declared_kind_column(self):
        """The second column is GONE, not merely left unwritten.

        Stated over the model's own fields rather than over any one reader: a
        reader that simply stopped consulting the second column would leave it
        on the table for the next reader to find, which is the shape this
        collapse exists to remove.
        """
        assert {f.name for f in Task._meta.get_fields()
                if f.name.endswith("_type")} == {"task_type"}

    def test_the_declared_kind_is_immutable_on_a_unit_with_no_parent(self):
        t, c = self._tc()
        unit = self._unit(t, c, "invoice_batch")
        unit.task_type = "receipt_scan"
        with pytest.raises(ValueError, match="task_type is immutable"):
            unit.save()

    def test_the_declared_kind_is_immutable_on_a_contained_unit(self):
        """One guard now, at the other altitude — the case that used to have a
        second guard of its own because it had a second column of its own."""
        t, c = self._tc()
        parent = self._unit(t, c, "invoice_batch")
        contained = self._unit(t, c, "ocr", parent=parent)
        contained.task_type = "classify"
        with pytest.raises(ValueError, match="task_type is immutable"):
            contained.save()

    def test_unrelated_field_still_saves(self):
        t, c = self._tc()
        unit = self._unit(t, c, "invoice_batch")
        unit.event_count = 5
        unit.save()
        unit.refresh_from_db()
        assert unit.event_count == 5

    # --- two altitudes, and no third --------------------------------------

    def test_a_contained_unit_carrying_a_kind_cannot_itself_contain(self):
        """Depth stays at two levels, and the collapse is what makes this
        worth restating rather than leaving to the untyped case beside it.

        A contained unit now carries its kind in the very column a whole unit
        of work carries one in, so *"it has a declared kind"* no longer tells
        the two altitudes apart. Only ``parent`` does — which is exactly what
        the refusal reads.
        """
        t, c = self._tc()
        parent = TaskService.create_task(
            tenant=t, customer=c, balance_snapshot_micros=0,
            task_type="invoice_batch")
        contained = TaskService.create_task(
            tenant=t, customer=c, balance_snapshot_micros=0, parent=parent,
            task_type="ocr")
        assert contained.task_type == "ocr"
        with pytest.raises(ValueError, match="depth"):
            TaskService.create_task(
                tenant=t, customer=c, balance_snapshot_micros=0,
                parent=contained, task_type="classify")

    # --- the discriminator on the declaration -----------------------------

    def test_the_discriminator_offers_exactly_the_registrys_two_values(self):
        """The model's own choices against the generated registry — a claim
        across two modules, so a third value written locally goes red.

        That the values are held by IMPORT rather than restated is a separate
        claim with a separate owner: the consumer census walks the references
        themselves, and a second copy of that walk here would only agree with
        it.
        """
        assert {value for value, _ in TASK_TYPE_KIND_CHOICES} \
            == TASK_TYPE_KIND_VALUES

    def test_one_word_may_name_a_kind_of_work_at_either_altitude(self):
        """Why the discriminator earns its keep once the columns collapse.

        The declaration's uniqueness key carries ``kind``, so the same word is
        two different declarations — one meant for a whole unit of work, one
        meant for contained work — each with its own policy. That is the fact
        a unit's single column can no longer carry, and the reason it stays on
        the declaration.
        """
        t, _ = self._tc()
        whole = TaskType.objects.create(tenant=t, key="ocr",
                                        kind=TASK_TYPE_KIND_TASK)
        contained = TaskType.objects.create(tenant=t, key="ocr",
                                            kind=TASK_TYPE_KIND_SUBTASK)
        assert whole.id != contained.id
        assert {tt.kind for tt in TaskType.objects.filter(tenant=t, key="ocr")} \
            == TASK_TYPE_KIND_VALUES

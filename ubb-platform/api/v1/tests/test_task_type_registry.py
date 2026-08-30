"""The kind-of-work registry, at the root and with a frozen regime (#414).

Two things land together here and each has to be proved on its own. The
DECLARATION gains `pricing_mode` — how a kind of work is sold, per event or at
one agreed price — and it can never be changed afterwards. The SURFACE moves
from `/api/v1/metering/task-types` to `/api/v1/task-types`, keeping its
`metering` product gate and its Admin write floor, because the mount and the
gate are different questions.

⚠ The mount is available exactly once (ADR-0007 §3), so *the old path is gone*
is asserted rather than assumed: a surface answering on both would be the
provisional public shape that ADR forbids, and nothing else in CI compares the
two paths.
"""
import pytest
from django.core.exceptions import ValidationError
from django.test import Client

from api.v1.api import api
from api.v1.schemas import TaskTypeIn, TaskTypeOut
from api.v1.task_type_endpoints import task_type_router
from apps.platform.audit.models import AuditRecord
from apps.platform.grouping_fields.models import GroupingField
from apps.platform.membership.roles import ADMIN, WRITE
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.work.models import TaskType
from core.problems import PROBLEMS
from core.vocabulary import (
    PRICING_MODE_EVENT_PRICED, PRICING_MODE_FIXED, TASK_TYPE_KIND_SUBTASK,
    TASK_TYPE_KIND_TASK)

REGISTRY = "/api/v1/task-types"
#: Where it used to be. Spelled once, so every assertion that the old surface is
#: gone is talking about the same path.
RETIRED_PATH = "/api/v1/metering/task-types"
#: The reporting surface that deliberately did NOT come with it: it belongs to
#: the analytics collapse, and moving it now would break a path twice.
JOB_ANALYTICS = "/api/v1/metering/analytics/tasks"


@pytest.mark.django_db
class TestTaskTypeRegistry:
    def setup_method(self):
        # products=[...] is REQUIRED — the routes are gated by _product_check,
        # so a tenant without "metering" gets 403, not 422.
        self.tenant = Tenant.objects.create(name="T", products=["metering"])
        self.key, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.client = Client()
        # required_dimensions is validated against the Grouping Field registry
        # (slot_map) — "region" must exist before a kind of work can require it.
        GroupingField.objects.create(tenant=self.tenant, key="region",
                                     slot="grouping_field_1", scope="task")

    # -- helpers ---------------------------------------------------------

    def _auth(self, raw=None):
        return {"HTTP_AUTHORIZATION": f"Bearer {raw or self.raw_key}"}

    def _get(self, path, raw=None):
        return self.client.get(path, **self._auth(raw))

    def _put(self, path, data, raw=None):
        return self.client.put(path, data=data, content_type="application/json",
                               **self._auth(raw))

    def _declare(self, *items, raw=None):
        return self._put(REGISTRY, {"task_types": list(items)}, raw=raw)

    def _held(self, key, kind=TASK_TYPE_KIND_TASK):
        return next(row for row in self._get(REGISTRY).json()["task_types"]
                    if row["key"] == key and row["kind"] == kind)

    # -- the declaration -------------------------------------------------

    def test_put_declares_types(self):
        r = self._declare(
            {"key": "invoice_batch", "kind": TASK_TYPE_KIND_TASK,
             "default_provider_cost_limit_micros": 5_000_000,
             "required_dimensions": ["region"]},
            {"key": "ocr", "kind": TASK_TYPE_KIND_SUBTASK,
             "default_provider_cost_limit_micros": 2_000_000})
        assert r.status_code == 200
        assert TaskType.objects.filter(tenant=self.tenant).count() == 2

    def test_put_is_idempotent(self):
        body = {"key": "invoice_batch", "kind": TASK_TYPE_KIND_TASK,
                "default_provider_cost_limit_micros": 5_000_000}
        self._declare(body)
        self._declare(body)
        assert TaskType.objects.filter(tenant=self.tenant).count() == 1

    def test_put_updates_the_ceiling(self):
        TaskType.objects.create(tenant=self.tenant, key="invoice_batch",
                                kind=TASK_TYPE_KIND_TASK,
                                default_provider_cost_limit_micros=1_000_000)
        self._declare({"key": "invoice_batch", "kind": TASK_TYPE_KIND_TASK,
                       "default_provider_cost_limit_micros": 9_000_000})
        assert TaskType.objects.get(
            tenant=self.tenant, key="invoice_batch"
        ).default_provider_cost_limit_micros == 9_000_000

    def test_undeclared_required_dimension_is_422(self):
        # "region" is pre-declared in setup_method; "customer_tier" is not —
        # the point of this test is that an UNdeclared key is rejected.
        r = self._declare({"key": "invoice_batch", "kind": TASK_TYPE_KIND_TASK,
                           "required_dimensions": ["customer_tier"]})
        assert r.status_code == 422
        assert "not declared" in r.json()["detail"]

    def test_get_lists_types(self):
        TaskType.objects.create(tenant=self.tenant, key="ocr",
                                kind=TASK_TYPE_KIND_SUBTASK)
        r = self._get(REGISTRY)
        assert r.status_code == 200
        assert r.json()["task_types"][0]["key"] == "ocr"

    def test_put_is_atomic_across_items(self):
        """Override 2: a two-item PUT whose second item is invalid must leave
        ZERO TaskType rows from the first item — the whole loop plus the
        audit write happen inside one transaction.atomic()."""
        r = self._declare(
            {"key": "invoice_batch", "kind": TASK_TYPE_KIND_TASK,
             "default_provider_cost_limit_micros": 5_000_000},
            {"key": "ocr", "kind": TASK_TYPE_KIND_SUBTASK,
             "required_dimensions": ["undeclared_dim"]})
        assert r.status_code == 422
        assert TaskType.objects.filter(tenant=self.tenant).count() == 0

    # -- how a kind of work is sold --------------------------------------

    def test_a_declaration_that_says_nothing_is_priced_per_event(self):
        """Every kind of work declared before this field existed was declared
        when per-event was the only regime there was, so the field's absence
        means that and not *nobody said*."""
        self._declare({"key": "invoice_batch", "kind": TASK_TYPE_KIND_TASK})
        assert self._held("invoice_batch")["pricing_mode"] == (
            PRICING_MODE_EVENT_PRICED)

    def test_a_kind_of_work_can_be_sold_at_one_agreed_price(self):
        self._declare({"key": "transcode", "kind": TASK_TYPE_KIND_TASK,
                       "pricing_mode": PRICING_MODE_FIXED})
        assert self._held("transcode")["pricing_mode"] == PRICING_MODE_FIXED

    def test_changing_how_a_kind_of_work_is_sold_is_refused(self):
        """AC 2 at the surface — its own code and its own status.

        409 rather than 422 because the request is well formed and what refuses
        it is the state of a row that already exists; its own code rather than
        `validation_error` because this route already answers that for two
        unrelated things, and a caller cannot act on a code that means three.
        """
        self._declare({"key": "transcode", "kind": TASK_TYPE_KIND_TASK,
                       "pricing_mode": PRICING_MODE_FIXED})
        r = self._declare({"key": "transcode", "kind": TASK_TYPE_KIND_TASK,
                           "pricing_mode": PRICING_MODE_EVENT_PRICED})
        body = r.json()
        assert r.status_code == PROBLEMS["pricing_mode_frozen"]["status"] == 409
        assert body["code"] == "pricing_mode_frozen"
        assert body["key"] == "transcode"
        assert body["pricing_mode"] == PRICING_MODE_FIXED
        assert self._held("transcode")["pricing_mode"] == PRICING_MODE_FIXED

    def test_a_refused_regime_change_leaves_the_rest_of_the_body_unwritten(self):
        """The refusal is raised inside the transaction, not returned from it.

        Otherwise a body declaring three new kinds of work and re-selling a
        fourth would half-apply, and the tenant's registry would end up in a
        state no request asked for.
        """
        self._declare({"key": "transcode", "kind": TASK_TYPE_KIND_TASK,
                       "pricing_mode": PRICING_MODE_FIXED})
        r = self._declare(
            {"key": "brand-new", "kind": TASK_TYPE_KIND_TASK},
            {"key": "transcode", "kind": TASK_TYPE_KIND_TASK,
             "pricing_mode": PRICING_MODE_EVENT_PRICED})
        assert r.status_code == 409
        assert not TaskType.objects.filter(tenant=self.tenant,
                                           key="brand-new").exists()

    def test_omitting_the_regime_keeps_it_rather_than_re_selling_per_event(self):
        """⚠ THE CASE A DEFAULTED `pricing_mode` WOULD HAVE BROKEN, and it is
        the one an existing integration walks into first.

        This surface's whole shape is *send the vocabulary again*, so a client
        written before this field existed — or one that simply does not set it —
        omits the regime on every call. If the absence materialised
        `event_priced`, that client would be trying to re-sell every `fixed`
        kind of work per event, be refused by the frozen rule for a word it
        never used, and be locked out of ever revising that kind of work's
        ceiling or windows again.

        Asserted through a body that DOES change something, so the case cannot
        pass by the call being a no-op: the ceiling moves and the regime does
        not.
        """
        self._declare({"key": "transcode", "kind": TASK_TYPE_KIND_TASK,
                       "pricing_mode": PRICING_MODE_FIXED})
        r = self._declare({"key": "transcode", "kind": TASK_TYPE_KIND_TASK,
                           "default_provider_cost_limit_micros": 6_000_000})
        assert r.status_code == 200
        held = self._held("transcode")
        assert held["pricing_mode"] == PRICING_MODE_FIXED
        assert held["default_provider_cost_limit_micros"] == 6_000_000

    def test_a_new_kind_of_work_that_names_no_regime_is_event_priced(self):
        """The other half of the same field, and the column's own default is
        what answers — every declaration made before this field existed was
        made when per-event was the only regime there was."""
        self._declare({"key": "brand-new", "kind": TASK_TYPE_KIND_TASK})
        assert self._held("brand-new")["pricing_mode"] == (
            PRICING_MODE_EVENT_PRICED)

    def test_the_ledger_entry_covers_every_field_of_a_declaration(self):
        """A field added to `TaskTypeIn` must not reach the row and miss the
        ledger.

        The entry is built from the declaration's own fields rather than from a
        second list of their names, and this is what holds that: the day
        somebody adds a field to the schema and hand-writes the entry instead,
        the two sets disagree here. Asserted as an exact set, because an entry
        carrying a key the declaration does not have is the same defect read
        the other way.
        """
        self._declare({"key": "transcode", "kind": TASK_TYPE_KIND_TASK})
        entry = AuditRecord.objects.filter(tenant_id=self.tenant.id).latest(
            "created_at")
        assert set(entry.metadata["task_types"][0]) == set(
            TaskTypeIn.model_fields)

    def test_one_body_naming_a_declaration_twice_is_refused_by_the_route(self):
        """The loop has to read its own writes, and the failure is invisible.

        Nothing refuses a repeated `(kind, key)` in one body — the field is a
        list — so the second occurrence is a re-declaration of a row the first
        occurrence has just created. A refusal that only consulted the rows read
        BEFORE the loop would see nothing standing, skip the check, and hand the
        change to the trigger, which answers with an integrity error and a 500
        instead of the 409 that names the next step. Asserted as a 409 with the
        code rather than merely `!= 500`, because the wrong answer here is a
        plausible one.
        """
        r = self._declare(
            {"key": "transcode", "kind": TASK_TYPE_KIND_TASK,
             "pricing_mode": PRICING_MODE_FIXED},
            {"key": "transcode", "kind": TASK_TYPE_KIND_TASK,
             "pricing_mode": PRICING_MODE_EVENT_PRICED})
        assert r.status_code == 409
        assert r.json()["code"] == "pricing_mode_frozen"
        assert not TaskType.objects.filter(tenant=self.tenant).exists()

    def test_re_sending_the_same_declaration_is_not_a_change(self):
        """The whole surface is *send the vocabulary again*, so the frozen rule
        has to let an unchanged regime through — at the route AND at the
        database, which is why this asserts a 200 rather than merely no 409."""
        body = {"key": "transcode", "kind": TASK_TYPE_KIND_TASK,
                "pricing_mode": PRICING_MODE_FIXED,
                "default_provider_cost_limit_micros": 4_000_000}
        assert self._declare(body).status_code == 200
        assert self._declare(
            {**body, "default_provider_cost_limit_micros": 8_000_000}
        ).status_code == 200
        assert self._held("transcode")["pricing_mode"] == PRICING_MODE_FIXED
        assert self._held("transcode")[
            "default_provider_cost_limit_micros"] == 8_000_000

    def test_the_two_altitudes_are_sold_independently(self):
        """One word at two altitudes is two declarations, so the frozen rule
        binds each row and never the key."""
        assert self._declare(
            {"key": "transcode", "kind": TASK_TYPE_KIND_TASK,
             "pricing_mode": PRICING_MODE_FIXED},
            {"key": "transcode", "kind": TASK_TYPE_KIND_SUBTASK,
             "pricing_mode": PRICING_MODE_EVENT_PRICED}).status_code == 200
        assert self._held("transcode", TASK_TYPE_KIND_TASK)[
            "pricing_mode"] == PRICING_MODE_FIXED
        assert self._held("transcode", TASK_TYPE_KIND_SUBTASK)[
            "pricing_mode"] == PRICING_MODE_EVENT_PRICED

    # -- retire and redeclare, which is what freezing costs ---------------

    def test_retiring_and_declaring_a_replacement_leaves_both_rows(self):
        """AC 5, and the whole reason this registry needs no publish record.

        Changing how a kind of work is sold is a retirement plus a new
        declaration. What that leaves behind is two readable rows — the old one
        carrying the instant it stopped being offered, the new one live — which
        is exactly the *when did this change, and to what* a publish record
        exists to answer.
        """
        self._declare({"key": "transcode-v1", "kind": TASK_TYPE_KIND_TASK,
                       "pricing_mode": PRICING_MODE_EVENT_PRICED})
        r = self._declare(
            {"key": "transcode-v1", "kind": TASK_TYPE_KIND_TASK,
             "pricing_mode": PRICING_MODE_EVENT_PRICED, "retired": True},
            {"key": "transcode-v2", "kind": TASK_TYPE_KIND_TASK,
             "pricing_mode": PRICING_MODE_FIXED})
        assert r.status_code == 200

        old, new = self._held("transcode-v1"), self._held("transcode-v2")
        assert old["retired"] is True and old["retired_at"] is not None
        assert old["pricing_mode"] == PRICING_MODE_EVENT_PRICED
        assert new["retired"] is False and new["retired_at"] is None
        assert new["pricing_mode"] == PRICING_MODE_FIXED

    def test_a_retired_kind_of_work_is_still_readable(self):
        """Retire-never-delete: work already done under it still refers to it,
        and a replacement beside it is only a record of a change if the retired
        row can still be read."""
        self._declare({"key": "transcode-v1", "kind": TASK_TYPE_KIND_TASK})
        self._declare({"key": "transcode-v1", "kind": TASK_TYPE_KIND_TASK,
                       "retired": True})
        listed = self._get(REGISTRY).json()["task_types"]
        assert [row["key"] for row in listed] == ["transcode-v1"]
        assert listed[0]["retired"] is True

    def test_re_retiring_does_not_move_the_instant(self):
        """An idempotent PUT must not slide the record forward.

        The surface's whole shape is *send the vocabulary again*, so a rule that
        re-stamped on every call would leave a tenant unable to say when
        anything was actually retired — which is the fact the frozen regime
        leans on.
        """
        self._declare({"key": "transcode-v1", "kind": TASK_TYPE_KIND_TASK})
        self._declare({"key": "transcode-v1", "kind": TASK_TYPE_KIND_TASK,
                       "retired": True})
        stamped = self._held("transcode-v1")["retired_at"]
        self._declare({"key": "transcode-v1", "kind": TASK_TYPE_KIND_TASK,
                       "retired": True})
        assert self._held("transcode-v1")["retired_at"] == stamped

    def test_saying_nothing_about_retirement_leaves_it_alone(self):
        """The third answer, and the reason `retired` is nullable.

        A caller that has never heard of the field sends the same body it always
        sent. If the absent field read as `false`, that body would silently
        bring every retired kind of work back into use.
        """
        self._declare({"key": "transcode-v1", "kind": TASK_TYPE_KIND_TASK,
                       "retired": True})
        stamped = self._held("transcode-v1")["retired_at"]
        self._declare({"key": "transcode-v1", "kind": TASK_TYPE_KIND_TASK,
                       "default_provider_cost_limit_micros": 3_000_000})
        assert self._held("transcode-v1")["retired_at"] == stamped

    def test_a_kind_of_work_can_be_brought_back(self):
        self._declare({"key": "transcode-v1", "kind": TASK_TYPE_KIND_TASK,
                       "retired": True})
        self._declare({"key": "transcode-v1", "kind": TASK_TYPE_KIND_TASK,
                       "retired": False})
        held = self._held("transcode-v1")
        assert held["retired"] is False and held["retired_at"] is None

    def test_the_ledger_records_what_each_item_declared(self):
        """One action for the whole request, and the per-item detail beside it.

        Why there is no second action for a retirement is argued once, at
        `audit_record` in `api/v1/task_type_endpoints.py`. What this pins is the
        consequence: a call that declares one kind of work and retires another
        records both, per item, which is the only place a reader could tell them
        apart.
        """
        self._declare(
            {"key": "transcode-v1", "kind": TASK_TYPE_KIND_TASK,
             "retired": True},
            {"key": "transcode-v2", "kind": TASK_TYPE_KIND_TASK,
             "pricing_mode": PRICING_MODE_FIXED})
        entry = AuditRecord.objects.filter(tenant_id=self.tenant.id).latest(
            "created_at")
        assert entry.action == "task_type.declared"
        assert [(item["key"], item["pricing_mode"], item["retired"])
                for item in entry.metadata["task_types"]] == [
            ("transcode-v1", PRICING_MODE_EVENT_PRICED, True),
            ("transcode-v2", PRICING_MODE_FIXED, None)]

    # -- where it sits, and what still guards it -------------------------

    def test_the_metering_prefixed_path_is_gone(self):
        """AC 3 — the move, not a second surface.

        Answering on both paths would be the provisional public shape ADR-0007
        §3 forbids, and it is the failure a purely additive change would leave
        behind unnoticed: every other assertion in this module would pass.
        """
        assert self._get(RETIRED_PATH).status_code == 404
        assert self._put(RETIRED_PATH,
                         {"task_types": [{"key": "x",
                                          "kind": TASK_TYPE_KIND_TASK}]}
                         ).status_code == 404

    def test_job_analytics_stays_behind_the_metering_prefix(self):
        """AC 4 — the reporting surface did not come with the registry.

        Both directions, because "it still answers there" and "it did not also
        appear at the root" are two different ways for this to have gone wrong.
        """
        assert self._get(JOB_ANALYTICS).status_code == 200
        assert self._get("/api/v1/analytics/tasks").status_code == 404

    def test_a_tenant_that_does_not_meter_is_refused(self):
        """AC 3 — the product gate came with the mount.

        ⚠ THE TENANT HAS TO BE MADE THROUGH `QuerySet.update()`, because
        `Tenant.save` calls `clean` and `clean` refuses to store products
        without metering. That is asserted below as well, so a reader knows the
        shape is unreachable from outside rather than merely unusual — but the
        gate itself is proved by driving a real request through it, which is
        the half an argument cannot supply.
        """
        Tenant.objects.filter(id=self.tenant.id).update(products=["billing"])
        assert self._get(REGISTRY).status_code == 403
        assert self._declare({"key": "x", "kind": TASK_TYPE_KIND_TASK}
                             ).status_code == 403

    def test_no_tenant_can_reach_that_state_through_the_model(self):
        with pytest.raises(ValidationError) as refused:
            Tenant.objects.create(name="No metering", products=["billing"])
        assert "metering" in str(refused.value)

    def test_a_write_below_admin_is_refused_and_a_read_is_not(self):
        """AC 3 — the Admin write floor came with the mount too.

        Both halves in one case, because a floor that refused the read as well
        would satisfy the refusal on its own and would be a different bug: a
        declaration decides how usage is costed, which is why the write is
        Admin, and reading the vocabulary is not a pricing change.
        """
        writer, raw = TenantApiKey.create_key(self.tenant, label="writer")
        writer.role = WRITE
        writer.save(update_fields=["role"])

        assert self.key.role == ADMIN
        assert self._declare({"key": "x", "kind": TASK_TYPE_KIND_TASK},
                             raw=raw).status_code == 403
        assert self._get(REGISTRY, raw=raw).status_code == 200

    def test_an_unauthenticated_caller_reaches_neither_route(self):
        assert self.client.get(REGISTRY).status_code == 401
        assert self.client.put(REGISTRY, data={"task_types": []},
                               content_type="application/json").status_code == 401

    def test_one_tenants_vocabulary_is_invisible_to_another(self):
        other = Tenant.objects.create(name="Other", products=["metering"])
        TaskType.objects.create(tenant=other, key="theirs",
                                kind=TASK_TYPE_KIND_TASK)
        assert self._get(REGISTRY).json()["task_types"] == []


@pytest.mark.django_db
class TestTheRegistryMintsNoThirdPublishMechanism:
    """AC 6 — no publish record, no draft state, no effective-dating.

    ⚠ ASSERTED AS EXACT SETS RATHER THAN AS ABSENCES OF NAMES NOBODY PROPOSED.
    A case listing forbidden words would pass over `staged_at`, `revision` or
    any other spelling of the same idea; the whole point of §10's ruling is that
    this registry has ONE way to change a declaration and one way to stop
    offering it, so the surface's shape is the claim and the shape is what is
    pinned. It goes red when a route or a field is added, which is when a person
    should read it.
    """

    def test_the_registry_publishes_exactly_two_operations(self):
        assert {(method, path)
                for path, operation in task_type_router.path_operations.items()
                for view in operation.operations
                for method in view.methods} == {("PUT", "/task-types"),
                                                ("GET", "/task-types")}

    def test_the_declaration_carries_exactly_these_fields(self):
        assert set(TaskTypeIn.model_fields) == {
            "key", "kind", "pricing_mode", "default_provider_cost_limit_micros",
            "silence_window_seconds", "absolute_deadline_seconds",
            "required_dimensions", "retired"}
        assert set(TaskTypeOut.model_fields) == {
            "key", "kind", "pricing_mode", "default_provider_cost_limit_micros",
            "silence_window_seconds", "absolute_deadline_seconds",
            "required_dimensions", "retired", "retired_at"}

    def test_the_registry_is_mounted_at_the_root(self):
        """The mount, read off the assembled API rather than off this module.

        Asserting the router's own paths would be asserting what the file above
        says; what a tenant reaches depends on the prefix `api.py` mounts it
        under, and that is the half that could be wrong.
        """
        assert [prefix for prefix, router in api._routers
                if router is task_type_router] == [""]

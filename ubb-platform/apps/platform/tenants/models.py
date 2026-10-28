import hashlib
import secrets

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import models

from apps.platform.membership.roles import ADMIN, ROLE_CHOICES
from core.exceptions import StripeFatalError
from core.currency_policy import (
    UnsupportedCurrency,
    admit_currency,
    usd_only_check,
)
from core.models import BaseModel
from core.transitions import FROZEN
from core.vocabulary import (
    CUSTOMER_BILLING_MODE_EXTERNAL,
    CUSTOMER_BILLING_MODE_POSTPAID,
    CUSTOMER_BILLING_MODE_PREPAID,
    CUSTOMER_BILLING_MODE_VALUES,
    ENFORCEMENT_MODE_ENFORCING,
    ENFORCEMENT_MODE_OFF,
    PAYMENT_RAIL_ENVIRONMENT_LIVE,
    PAYMENT_RAIL_ENVIRONMENT_TEST,
    PAYMENT_RAIL_ENVIRONMENT_VALUES,
    PAYMENT_RAIL_STRIPE,
    PAYMENT_RAIL_VALUES,
    TENANT_POSTURE_FULL_BILLING,
    TENANT_POSTURE_METERING_ONLY,
    TENANT_PRODUCT_METERING,
    TENANT_PRODUCT_VALUES,
)


# Which products a tenant may enable is the registry's answer, not this
# model's: `TENANT_PRODUCT_VALUES` is imported from the generated
# `core.vocabulary` rather than restated here, so adding or removing a product
# is one edit in `domain-vocabulary/` instead of four across the surfaces that
# name the set. `clean` below validates against it and `save` defaults from it.
#
# "subscriptions" was retired 2026-07-27: it is not a standalone product but a
# capability of billing (a wrapper over Stripe Billing, valuable only next to
# metering and margin). Plans and subscription lifecycle gate on "billing".
# The second recording lane's flag went the same way in slice 1, with the lane
# it switched on (#149 §6) — there is one recording core, so there is nothing
# for a tenant to choose between.

# WHICH CURRENCY A TENANT MAY HOLD IS NOT THIS MODEL'S ANSWER, AND IT IS NOT
# `core.money`'s EITHER. That module's table says which currencies UBB can
# REPRESENT; `core.currency_policy` says which one its economics ADMIT, and in
# v1 that is US dollars only (ADR-0023). `clean` below asks the policy, and
# `ck_tenant_default_currency_usd` holds every write that never calls it — the
# admin form is a door, and so is `QuerySet.update()`.

# The canonical tokens come from the registry via `core.vocabulary` (#200), so
# this model cannot hold a second copy of a value that drifts from it. The
# English stays here: label wording is not registry content (ADR-0008 §4).
#
# All three by reference since slice 8 (R10-W3): the mode that meters and
# never bills is `external`, which says where the billing happens — the fact a
# tenant is choosing between — where the retired word said what UBB does not do.
BILLING_MODE_CHOICES = [
    (CUSTOMER_BILLING_MODE_EXTERNAL, "External billing"),
    (CUSTOMER_BILLING_MODE_PREPAID, "Prepaid credits"),
    (CUSTOMER_BILLING_MODE_POSTPAID, "Postpaid"),
]

#: WHETHER UBB CREATES THIS TENANT'S CUSTOMER CHARGES AT ALL — the registry's
#: `tenant_posture`, DERIVED from the billing mode and never stored (ADR-0006 §4):
#: a second writable copy could disagree with the first. Served read-only on
#: the tenant config so a caller need not reconstruct this mapping.
TENANT_POSTURE_OF = {
    CUSTOMER_BILLING_MODE_EXTERNAL: TENANT_POSTURE_METERING_ONLY,
    CUSTOMER_BILLING_MODE_PREPAID: TENANT_POSTURE_FULL_BILLING,
    CUSTOMER_BILLING_MODE_POSTPAID: TENANT_POSTURE_FULL_BILLING,
}

#: THE MODES IN WHICH UBB MOVES A TENANT'S CUSTOMER MONEY — the ones whose
#: posture is `full_billing` — and so the ones a tenant may not enter before
#: the payment rail they collect through is activated (ADR-0008 §6, G27).
#: Derived from the posture map rather than listed, so the two cannot disagree.
MONEY_MODES = frozenset(
    mode for mode, posture in TENANT_POSTURE_OF.items()
    if posture == TENANT_POSTURE_FULL_BILLING)

#: The rail a tenant's money modes collect through. v1 has one; a second rail
#: would make this a per-tenant choice, and that is a decision for then.
TENANT_MONEY_RAIL = PAYMENT_RAIL_STRIPE


def rail_environment_of(*, is_sandbox):
    """Which environment of the rail a tenant's money moves in (ruling 1).

    A sandbox exercises the rail's `test` environment and every other tenant
    its `live` one — so a sandbox copied from a `prepaid` parent needs the
    `test` activation, and a `live` one does not stand in for it.
    """
    return (PAYMENT_RAIL_ENVIRONMENT_TEST if is_sandbox
            else PAYMENT_RAIL_ENVIRONMENT_LIVE)


class PaymentRailNotActivated(ValidationError):
    """G27's refusal: a money mode, with no enabled activation of its rail.

    A `ValidationError` on `billing_mode`, so the admin form shows it on the
    field and a model's `clean()` raises it like any other; its own class,
    so the API answers it by name (`payment_rail_not_activated`) rather than
    as a generic invalid configuration, and a caller can tell "this mode is
    not open yet" from "you sent something malformed".
    """

    code = "payment_rail_not_activated"

    def __init__(self, *, billing_mode, rail, environment):
        self.billing_mode = billing_mode
        self.rail = rail
        self.environment = environment
        self.explanation = (
            f"billing_mode '{billing_mode}' moves customer money through the "
            f"'{rail}' payment rail, which has no enabled activation in its "
            f"'{environment}' environment. A rail is activated by a named "
            f"approver recording its evidence (ADR-0008 §6); until then this "
            f"tenant can meter and bill elsewhere ('external').")
        super().__init__({"billing_mode": [self.explanation]})


def refuse_a_money_mode_without_its_rail(*, billing_mode, is_sandbox):
    """THE ONE DOMAIN RULE G27 is (ADR-0008 §6; the owner's ruling 3).

    `prepaid` or `postpaid` may not be entered without an ENABLED activation
    of the tenant's rail in the tenant's environment. Every door that writes
    a tenant reaches it through `Tenant.clean()` — the config route, sandbox
    creation, the admin form and the seed command — and
    `trg_tenant_money_mode_needs_its_rail` holds the same requirement for the
    writes that never call `clean()`. It decides nothing about a tenant
    already in a money mode: disabling a rail stops new use, and scans no
    dependent tenant (ruling 2).
    """
    if billing_mode not in MONEY_MODES:
        return
    environment = rail_environment_of(is_sandbox=is_sandbox)
    if not the_rail_is_open_in(environment):
        raise PaymentRailNotActivated(
            billing_mode=billing_mode, rail=TENANT_MONEY_RAIL,
            environment=environment)


def the_rail_is_open_in(environment):
    """Whether the tenant money rail may be used in ``environment`` now: an
    activation exists AND its flag is on. The one read every G27 decision
    takes — entering a money mode, and starting new money on the rail.

    There is exactly one activation per rail and environment
    (`uq_payment_rail_activation_once_per_environment`), so this asks one
    row and never depends on which of two rows a query returns first.
    """
    return PaymentRailActivation.objects.filter(
        rail=TENANT_MONEY_RAIL, environment=environment, enabled=True).exists()


class PaymentRailClosed(StripeFatalError):
    """G27's OPERATIONAL refusal: new customer money on a rail that is closed —
    never activated, or its flag turned off — in the tenant's environment.

    The flag's one meaning is "may this rail be used now": ADR-0008 §6's
    flag "technically prevents premature use", and disabling it "may stop
    new activation or use of the rail" (the owner's ruling 2). So a tenant
    already in a money mode keeps its mode — nothing scans it — but no NEW
    money moves on a closed rail: no top-up checkout, no auto top-up
    charge, no usage invoice pushed, no subscription started, resumed or
    re-priced. Money that already moved still lands (webhooks, receipts),
    and stopping money (pause, cancel) is never refused.

    A `StripeFatalError` — not retryable, and raised before anything is
    sent — so every caller's non-retryable path takes it; the API answers it
    by name, with the same code as the entry refusal.
    """

    code = "payment_rail_not_activated"

    def __init__(self, *, tenant_id, rail, environment):
        self.rail = rail
        self.environment = environment
        self.explanation = (
            f"the '{rail}' payment rail is not open in its '{environment}' "
            f"environment — no enabled activation — so UBB starts no new "
            f"money movement on it for tenant {tenant_id}. Money already "
            f"moved still lands; an approver reopens the rail with its flag.")
        super().__init__(self.explanation)


def refuse_a_rail_operation_while_it_is_closed(tenant):
    """Refuse NEW customer money on ``tenant``'s rail unless it is open for
    the tenant's environment (G27's flag, operationally). Called by each
    outbound adapter before anything reaches Stripe.

    It governs the MONEY MODES, the posture G27 is about ("`prepaid` and
    `postpaid` may not be enabled without a matching activation"): a tenant in
    one moves its customers' money on the rail, and a closed rail stops that.
    An `external` tenant has entered no money mode, and UBB's subscription
    control plane serves it on the billing product as before — whether that
    use should need an activation too is the owner's question, recorded on
    #619, not a reading taken here.
    """
    if tenant.billing_mode not in MONEY_MODES:
        return
    environment = rail_environment_of(is_sandbox=tenant.is_sandbox)
    if not the_rail_is_open_in(environment):
        raise PaymentRailClosed(tenant_id=tenant.id, rail=TENANT_MONEY_RAIL,
                                environment=environment)


class PaymentRailActivation(BaseModel):
    """The evidence that a payment rail was approved to move money in one
    environment (ADR-0008 §6) — and the flag that lets it be used.

    **A record and a flag, on one row, under two rules.** The record —
    `rail`, `environment`, `activated_at`, `approved_by`, `evidence` — is
    historical fact: who approved what, when, on what evidence. All five are
    declared `FROZEN` and held by
    `trg_payment_rail_activation_declared_transitions` through every door
    (the owner's ruling 2). The flag, `enabled`, is the operational switch:
    turning it off stops any tenant ENTERING a money mode on this rail and
    environment, and deletes nothing — there is no delete or revoke path:
    the table refuses every `DELETE` (`trg_payment_rail_activation_is_kept`),
    the admin grants no delete permission, and nothing scans the tenants
    already in one.

    It has no tenant: a rail is activated for the platform, once per
    environment, and every tenant's money mode reads the one row for its
    own environment (`rail_environment_of`).
    """

    rail = models.CharField(
        max_length=20,
        choices=[(rail, rail) for rail in sorted(PAYMENT_RAIL_VALUES)])
    environment = models.CharField(
        max_length=10,
        choices=[(environment, environment)
                 for environment in sorted(PAYMENT_RAIL_ENVIRONMENT_VALUES)])
    activated_at = models.DateTimeField()
    approved_by = models.CharField(max_length=255)
    evidence = models.TextField()
    enabled = models.BooleanField(default=True)

    #: The evidence is history; the flag beside it is not, and is left
    #: undeclared for that reason — an operational column, the way a
    #: Charge's `correction_note` is.
    transition_classes = {
        "rail": FROZEN,
        "environment": FROZEN,
        "activated_at": FROZEN,
        "approved_by": FROZEN,
        "evidence": FROZEN,
    }

    class Meta:
        db_table = "ubb_payment_rail_activation"
        constraints = [
            # One activation per rail and environment: the flag answers
            # "may this rail be used here?" and two rows would make that
            # question ambiguous.
            models.UniqueConstraint(
                fields=["rail", "environment"],
                name="uq_payment_rail_activation_once_per_environment"),
            models.CheckConstraint(
                condition=models.Q(rail__in=sorted(PAYMENT_RAIL_VALUES)),
                name="ck_payment_rail_activation_rail_known"),
            models.CheckConstraint(
                condition=models.Q(
                    environment__in=sorted(PAYMENT_RAIL_ENVIRONMENT_VALUES)),
                name="ck_payment_rail_activation_environment_known"),
            # Evidence with no approver, or an approver with no evidence, is
            # not evidence (ADR-0008 §6: "a named approver").
            models.CheckConstraint(
                condition=~models.Q(approved_by=""),
                name="ck_payment_rail_activation_names_its_approver"),
            models.CheckConstraint(
                condition=~models.Q(evidence=""),
                name="ck_payment_rail_activation_carries_its_evidence"),
        ]

    def __str__(self):
        state = "enabled" if self.enabled else "disabled"
        return f"{self.rail} ({self.environment}, {state})"

# Tier-2 real-time spend control (D1): the SINGLE program kill switch — two
# positions (#42, spec §G; `advisory` retired, mapped to `off` by migration
# 0019).
#   off       — byte-for-byte pre-enforcement behavior: no counters, no
#               signals, no tagging — the live ledger / stop flag / per-task
#               cap are never touched.
#   enforcing — the full signal suite + state changes (task flips, start-gate
#               refusals, soft-floor gate, suspension, reapers).
# Read ONLY via apps.platform.tenants.flags (enforcement_mode/enforcing); no
# other flag exists. See docs/plans/2026-07-15-one-rule-enforcement-spec.md §G.
#
# The two are the registry's closed `enforcement_mode` (R10-W4), held here by
# reference — this file is the concept's declared backend consumer.
ENFORCEMENT_MODE_CHOICES = [
    (ENFORCEMENT_MODE_OFF, "Off"),
    (ENFORCEMENT_MODE_ENFORCING, "Enforcing"),
]


class Tenant(BaseModel):
    name = models.CharField(max_length=255)
    stripe_connected_account_id = models.CharField(max_length=255, blank=True, default="")
    # stripe_connected_account_id = tenant's own Stripe account (for end-user charges)
    # stripe_customer_id = tenant as UBB's customer (for platform fee billing)
    stripe_customer_id = models.CharField(max_length=255, blank=True, default="")
    platform_fee_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=1.00
    )
    is_active = models.BooleanField(default=True)
    branding_config = models.JSONField(default=dict)
    metadata = models.JSONField(default=dict)
    widget_secret = models.CharField(max_length=64, blank=True, default="")
    products = models.JSONField(default=list, blank=True)
    billing_mode = models.CharField(
        max_length=20, choices=BILLING_MODE_CHOICES,
        default=CUSTOMER_BILLING_MODE_EXTERNAL, db_index=True
    )
    default_currency = models.CharField(max_length=3, default="usd")
    charges_enabled = models.BooleanField(default=False)
    # F5.3: opt-in Stripe Tax passthrough. When True, automatic_tax={"enabled":
    # True} is sent at EXACTLY two charge sites — Subscription.create and the
    # postpaid usage Invoice.create. Tax computation/registration stays
    # entirely Stripe's job (the tenant configures Stripe Tax on their
    # connected account); UBB never computes tax. Top-up checkout /
    # PaymentIntents / receipts NEVER carry it: wallet credit must equal the
    # charged amount exactly.
    automatic_tax_enabled = models.BooleanField(default=False)
    # Tier-2 spend-control kill switch (D1). Default "off" = unchanged behavior.
    enforcement_mode = models.CharField(
        max_length=10, choices=ENFORCEMENT_MODE_CHOICES, default="off", db_index=True
    )
    # The live-counter-maintenance switch (#46, delivery spec §E;
    # NARROWED by #149 §6.5; renamed by #246):
    # governs REAL-TIME COUNTER MAINTENANCE — the synchronous live-counter
    # write on the recording path, the counter legs of both reconciles, and
    # the upward repair. It selects when the counters are maintained, never
    # which route an event takes in. ON: crossings
    # detected as the event is recorded, stop latency bounded independent of
    # drawdown-queue depth. OFF: the honest degraded posture — recording does
    # no live-counter Redis work; detection happens on the durable drawdown
    # lane, so latency degrades exactly when a runaway spender floods the
    # queue. The durable lane (drawdown detection, signal ledger, patrol,
    # webhook delivery, ack verdicts) NEVER switches off, and it maintains the
    # ack-verdict cache in both postures — flipping this never changes the
    # tenant-facing contract, only the latency profile. A behavior posture
    # beside enforcement_mode (products gates ACCESS; this selects behavior),
    # meaningful only when enforcing. Named for the arrival-time lane until
    # #246; that lane died in slice 1 and the switch never was its switch.
    # Read ONLY via apps.platform.tenants.flags.live_counter_maintenance_on.
    live_counter_maintenance_enabled = models.BooleanField(default=True)
    # THE TENANT'S OWN SILENCE WINDOW — how long a unit of work may go without
    # a metered event (heartbeat, stamped by accumulate_cost) before a sweeper
    # expires it. On Tenant (not RiskConfig) so the platform sweepers can read
    # it without importing billing. Lives here next to enforcement_mode.
    #
    # ⚠ IT IS NOW THE MIDDLE RUNG OF A LADDER, NOT THE ONLY ANSWER (#412).
    # `TaskType.silence_window_seconds` sits above it, so a tenant no longer has
    # to widen every kind of work to accommodate its slowest one; UBB's backstop
    # sits below it. NULL = this tenant declares nothing and the backstop
    # applies; 0 = the tenant declares that it wants no silence window at all,
    # which is the meaning it has always had here (the absolute deadline below
    # still applies, so 0 cannot produce an immortal unit).
    #
    # ⚠ THE COLUMN KEEPS ITS NAME, DELIBERATELY. The registry's word for the
    # STOP this window produces is `silence_window` and `reasons.py` holds it;
    # the registry declares no concept for the configuration, so there is no
    # canonical name for this column to be wrong about, and renaming a column
    # that no surface publishes is churn a later slice can take with the rest
    # of the tenant configuration if it wants it.
    task_stale_seconds = models.PositiveIntegerField(null=True, blank=True,
                                                     default=None)
    # THE TENANT'S OWN ABSOLUTE DEADLINE — how long a unit of work may run at
    # all, measured from creation and regardless of activity (#412). The middle
    # rung of the second ladder, under `TaskType.absolute_deadline_seconds` and
    # over UBB's backstop.
    #
    # ⚠ ZERO IS REFUSED HERE TOO, and for the reason the declaration states:
    # the absolute ceiling is the guard that stops any tenant getting an
    # immortal unit, so no rung may switch it off. NULL falls through to the
    # backstop; it is not a way to disable it.
    task_absolute_deadline_seconds = models.PositiveIntegerField(
        null=True, blank=True, default=None)
    # THE TENANT'S DEFAULT COGS CEILINGS FOR WORK WITH NO DECLARED KIND (#453,
    # slice 6 §2; moved here from billing's risk row on #141 §6.2's precedent —
    # the two rungs above, which is the argument: a ceiling is a kernel
    # concept, and a tenant that never enables billing still gets one).
    #
    # ⚠ THESE APPLY TO UNDECLARED WORK ONLY, which is what the `default_`
    # prefix says and what distinguishes them from the two rungs above. The
    # silence window and the absolute deadline are middle rungs UNDER a
    # declaration — a kind that says nothing about its window inherits the
    # tenant's. A declared kind of work must state its own ceiling or declare
    # itself uncapped (`TaskType.uncapped`), so there is nothing for it to
    # inherit and these are never consulted for it. The ladder for work with
    # no declared kind is: the caller's request (lower only) -> this rung, per
    # altitude -> no ceiling applies, and where no ceiling applies the unit's
    # assessment says `not_applicable` on every surface rather than staying
    # silent (#150 §8.2).
    #
    # One per altitude, because contained work legitimately costs a fraction
    # of the unit containing it. NULL = this tenant declares no default at that
    # altitude. Zero is refused at the tenant configuration route rather than
    # here, matching the declaration's own column.
    default_task_cogs_ceiling_micros = models.BigIntegerField(
        null=True, blank=True, default=None)
    default_subtask_cogs_ceiling_micros = models.BigIntegerField(
        null=True, blank=True, default=None)
    # ADMISSION CONTROL'S ONE SETTING (#462, slice 6 §1, §6; #154 §3.4): how
    # many NEW top-level pieces of work a seat may start in one minute. A
    # bound on how fast work enters is a property of the work's admission —
    # a kernel concept a tenant that does not bill through UBB is owed like
    # every other — so it lives here beside the tenant's other kernel rungs,
    # read by `work/admission.py` for every start. It sat on billing's risk
    # row until #462 (`gating/migrations/0015` carried each tenant's value
    # here), where the composition layer reached it only for a tenant with a
    # wallet, so a tenant without one had no bound at all.
    #
    # It bounds the RATE of new work and says nothing about supplier cost:
    # never spend protection, never a mitigation for the blind window. A
    # replay, contained work under admitted work, a usage report, a close and
    # configuration are never subject to it (#150 §1.3).
    #
    # NULL = this tenant declares no bound, which is what the risk row's
    # absence used to mean. Zero is refused at the tenant configuration
    # route, as the two ceiling rungs above refuse it: a bound of zero is not
    # a rate but a refusal of every start, and a suspension is the tool for
    # that.
    max_task_starts_per_minute = models.PositiveIntegerField(
        null=True, blank=True, default=None)
    # How far back a caller-supplied effective_at may reach (days). 0 = no
    # backfill at all (any past-dated effective_at is rejected); max 60 so a
    # backfill window never spans more than 3 calendar months (the reconcile
    # horizon of reconcile_cost_accumulators).
    backfill_window_days = models.PositiveIntegerField(default=34)
    # Sandbox mode (F4.4): a sandbox is a SIBLING Tenant row owned by its
    # parent_tenant. Because every domain model is tenant-scoped, isolation,
    # idempotency, rate limits and beat jobs all apply to the sandbox for free.
    # ubb_test_ keys are minted ON the sandbox tenant (routing at mint time).
    is_sandbox = models.BooleanField(default=False, db_index=True)
    # PROTECT: deleting a live tenant must never cascade-nuke its sandbox silently.
    parent_tenant = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT,
        related_name="sandboxes",
    )

    class Meta:
        db_table = "ubb_tenant"
        constraints = [
            # UBB v1 is USD-only (ADR-0023). The tenant's currency is the
            # column this rule most needs: the config route refuses another,
            # and the admin form edits every column without it.
            usd_only_check("default_currency", "ck_tenant_default_currency_usd"),
            # The closed set at the database (ADR-0002): `choices=` is a form
            # courtesy, and neither the admin form nor `QuerySet.update()` is
            # held by it.
            models.CheckConstraint(
                condition=models.Q(
                    billing_mode__in=sorted(CUSTOMER_BILLING_MODE_VALUES)),
                name="ck_tenant_billing_mode_known",
            ),
            models.UniqueConstraint(
                fields=["parent_tenant"],
                condition=models.Q(is_sandbox=True),
                name="uq_one_sandbox_per_parent",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(is_sandbox=True, parent_tenant__isnull=False)
                    | models.Q(is_sandbox=False, parent_tenant__isnull=True)
                ),
                name="ck_sandbox_iff_parent",
            ),
            # The absolute deadline is either undeclared at this rung or a real
            # window. See the column: no rung may switch the ceiling off, and
            # this is what makes that a property of the database rather than of
            # whichever code path last read it. There is deliberately no twin
            # for the silence window beside it — zero IS a declaration there,
            # and has been since that column was added.
            models.CheckConstraint(
                condition=models.Q(task_absolute_deadline_seconds__isnull=True)
                | models.Q(task_absolute_deadline_seconds__gt=0),
                name="ck_tenant_absolute_deadline_positive",
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def tenant_posture(self):
        """The registry's derived posture for this tenant's billing mode."""
        return TENANT_POSTURE_OF[self.billing_mode]

    @classmethod
    def from_db(cls, db, field_names, values):
        tenant = super().from_db(db, field_names, values)
        tenant._stored_money_posture = tenant._money_posture_as_loaded()
        return tenant

    def refresh_from_db(self, using=None, fields=None, from_queryset=None):
        super().refresh_from_db(using=using, fields=fields,
                                from_queryset=from_queryset)
        if fields is None or {"billing_mode", "is_sandbox"} & set(fields):
            self._stored_money_posture = self._money_posture_as_loaded()

    def _money_posture_as_loaded(self):
        """`(billing_mode, is_sandbox)` as read, or None if either was deferred."""
        loaded = self.__dict__
        if "billing_mode" not in loaded or "is_sandbox" not in loaded:
            return None
        return (loaded["billing_mode"], loaded["is_sandbox"])

    def _entering_a_money_mode(self):
        """Whether this write puts the tenant into a money mode it was not in.

        A new row in one is entering it, and so is a change of mode or of
        environment. A tenant already in one is not — re-saving it asks no
        question, which is what lets a rail be disabled without scanning
        anyone (ruling 2).
        """
        if self.billing_mode not in MONEY_MODES:
            return False
        stored = None
        if not self._state.adding:
            stored = getattr(self, "_stored_money_posture", None)
            if stored is None:
                stored = (Tenant.objects.filter(pk=self.pk)
                          .values_list("billing_mode", "is_sandbox").first())
        return stored != (self.billing_mode, self.is_sandbox)

    def clean(self):
        super().clean()
        if not self.products or TENANT_PRODUCT_METERING not in self.products:
            raise ValidationError({"products": "metering must always be present in products."})
        unknown = set(self.products) - TENANT_PRODUCT_VALUES
        if unknown:
            raise ValidationError(
                {"products": f"Unknown products: {', '.join(sorted(unknown))}"}
            )
        if self.billing_mode in MONEY_MODES and "billing" not in (self.products or []):
            raise ValidationError(
                {"billing_mode": f"billing_mode '{self.billing_mode}' requires 'billing' in products."}
            )
        # G27 (ADR-0008 §6): a money mode needs its rail activated first.
        if self._entering_a_money_mode():
            refuse_a_money_mode_without_its_rail(
                billing_mode=self.billing_mode, is_sandbox=self.is_sandbox)
        # UBB v1 is USD-only (ADR-0023). Every door that saves a tenant —
        # the config route, a sandbox, the admin form, a seed — reaches this,
        # and the CHECK above holds the writes that never call `save()`.
        try:
            self.default_currency = admit_currency(self.default_currency)
        except UnsupportedCurrency as refused:
            raise ValidationError({"default_currency": str(refused)})
        if self.backfill_window_days is not None and not (0 <= self.backfill_window_days <= 60):
            raise ValidationError(
                {"backfill_window_days": "backfill_window_days must be between 0 and 60."}
            )

    def save(self, *args, **kwargs):
        if not self.widget_secret:
            self.widget_secret = secrets.token_urlsafe(48)
        # Default to metering if no products set
        if not self.products:
            self.products = [TENANT_PRODUCT_METERING]
        # Sort and deduplicate products
        self.products = sorted(set(self.products))
        self.clean()
        super().save(*args, **kwargs)
        self._stored_money_posture = (self.billing_mode, self.is_sandbox)
        cache.delete(f"tenant_products:{self.id}")

    def rotate_widget_secret(self):
        """Generate a new widget_secret. Invalidates all existing widget JWTs."""
        self.widget_secret = secrets.token_urlsafe(48)
        self.save(update_fields=["widget_secret", "updated_at"])


class TenantApiKey(BaseModel):
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="api_keys"
    )
    key_prefix = models.CharField(max_length=20, db_index=True)
    key_hash = models.CharField(max_length=64, unique=True)
    label = models.CharField(max_length=255, blank=True, default="")
    is_active = models.BooleanField(default=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    # Tenant-principal role (identity build 1, #79). Both tenant-principal
    # schemes carry the same vocabulary; a key is the Admin-tier principal by
    # default and every pre-existing key migrates to "admin", so no key's reach
    # changes until floors bind across the surface (identity build 2). Role is
    # NOT selectable at mint time in this build.
    role = models.CharField(
        max_length=10, choices=ROLE_CHOICES, default=ADMIN
    )

    class Meta:
        db_table = "ubb_tenant_api_key"

    def __str__(self):
        return f"{self.key_prefix}... ({self.label})"

    @classmethod
    def create_key(cls, tenant, label="", is_test=False):
        """Create a new API key for a tenant. Returns (key_obj, raw_key).

        Sandbox routing happens HERE, at mint time (F4.4): a test key requested
        on a live tenant is minted on that tenant's sandbox sibling (lazily
        provisioned). After routing, the key mode must match the tenant mode —
        a live key can never exist on a sandbox tenant and vice versa.
        """
        if is_test and not tenant.is_sandbox:
            from apps.platform.tenants.services.sandbox_service import get_or_create_sandbox
            tenant = get_or_create_sandbox(tenant)
        if is_test != tenant.is_sandbox:
            raise ValueError(
                "API key mode must match tenant mode: "
                f"is_test={is_test} but tenant.is_sandbox={tenant.is_sandbox}"
            )
        prefix = "ubb_test_" if is_test else "ubb_live_"
        raw_key = prefix + secrets.token_urlsafe(32)
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        obj = cls.objects.create(
            tenant=tenant,
            key_prefix=raw_key[:16],
            key_hash=key_hash,
            label=label,
        )
        return obj, raw_key

    @classmethod
    def verify_key(cls, raw_key):
        """Verify a raw API key. Returns key object or None."""
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        try:
            key_obj = cls.objects.select_related("tenant").get(
                key_hash=key_hash, is_active=True, tenant__is_active=True
            )
        except cls.DoesNotExist:
            return None
        # Defense-in-depth (F4.4): create_key guarantees mode-matched keys, but
        # an ORM-crafted row must still never let a test key resolve to a live
        # tenant (or the reverse). key_prefix stores raw_key[:16], which always
        # contains the full ubb_test_/ubb_live_ prefix. tenant is already
        # select_related — zero extra queries.
        if key_obj.key_prefix.startswith("ubb_test_") != key_obj.tenant.is_sandbox:
            return None
        return key_obj


class ConnectOAuthState(BaseModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="connect_oauth_states")
    state = models.CharField(max_length=128, unique=True, db_index=True)
    return_url = models.CharField(max_length=2000, blank=True, default="")
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)

    class Meta:
        db_table = "ubb_connect_oauth_state"

"""Markup resolution — the last rung of the price ladder.

Precedence (design doc §5):

    customer override -> customer's Plan -> the tenant's declared default -> none

The plan rung is why a Personal Lite customer (50%) cannot silently bill at
the tenant default (20%). Plans live in the kernel, so reading them here is
an apps.platform.* import, not a cross-product one (ADR-001 rule 1).

**A RUNG ANSWERS A PERCENTAGE, ITS SOURCE AND THE RECORD IT CAME FROM, NEVER A
FINISHED NUMBER (#356, #357).** This module used to expose an applier that took
a supplier cost and handed back the marked-up figure, and the receipt writer at
the other end of it could only record that markup had happened — not which rung
supplied it, nor which record the percentage came from. Those are exactly what a
tenant asked *"why is this line £36?"* has to be shown, and they cannot be
reconstructed afterwards, because a markup record can be edited or withdrawn. So
the resolver takes the resolved value and applies it itself, with the percentage
and its source still in its hand at the point the record is built.

**AND A COST UBB HAS NOT RESOLVED NO LONGER REACHES HERE AT ALL.** The applier
carried a refusal for it (#328) because a markup is not a total: there is no
"at least" to state about a single price, so the honest answers were a real
basis or an error. The resolver now asks the question one step earlier and in
the vocabulary the answer belongs in — a margin over a cost UBB never learned is
a `waived` charge — so the case is decided before a percentage is even resolved,
and the refusal has no caller left to protect.

**THE TENANT-DEFAULT RUNG IS DECLARED, NOT INFERRED FROM AN ABSENCE (#357).**
It used to be the `customer IS NULL` row of the customer-override table — the
tenant default by being the one row with no customer on it. It is now its own
declared record, with its own routes and its own two audit actions, and the row
it replaces prices nothing. `TenantMarkup` survives this commit for its
per-customer rows alone and is deleted, with the plan catalog's two markup
columns, by the ticket that turns a customer override into a rule in the
customer's own Pricing Book.
"""
from dataclasses import dataclass

from apps.metering.pricing.models import TenantDefaultMarkup, TenantMarkup

#: WHICH RUNG SUPPLIED A PERCENTAGE — the value the receipt's provenance names.
#:
#: Named constants rather than three string literals because the receipt records
#: one of them, so they are part of what a stored record means rather than an
#: implementation detail of this module.
#:
#: **NOT A REGISTRY CONCEPT, AND THAT IS A DECISION WITH A DATE ON IT.** Two of
#: the three rungs below are being deleted: the customer override becomes a rule
#: in the customer's own Pricing Book, and the plan catalog's markup columns go
#: with the record above. Declaring a closed concept now would ratify a value
#: set that loses two of its three members inside this slice. They also cross no
#: typed surface — the receipt is published as an untyped record — so nothing
#: advertises them to a consumer who could switch on them.
MARKUP_RUNG_CUSTOMER = "customer"
MARKUP_RUNG_PLAN = "plan"
MARKUP_RUNG_TENANT_DEFAULT = "tenant_default"


@dataclass(frozen=True)
class ResolvedMarkup:
    """The markup that applies to one (tenant, customer), and where it came from.

    Frozen: instances are shared through the L1 cache and must never be mutated
    by a caller. ``source`` and ``source_id`` are carried for provenance — they
    answer "why was this event priced this way" without re-deriving the chain,
    and the receipt records both beside the percentage itself.
    """
    #: Millionths of a percent: 1_000_000 is 1%. Spelled the way the record it
    #: is read from spells it, and not under the money suffix — `_micros` means
    #: millionths of a CURRENCY unit, and two of the three records below still
    #: hide a percentage under it because they are about to be deleted.
    markup_micro_percent: int
    fixed_uplift_micros: int
    #: Which rung answered — one of the three constants above.
    source: str
    #: The id of the record the percentage was read from, as a string. A
    #: cross-reference and never a term: the record it names can be edited or
    #: withdrawn, which is exactly why the percentage travels by value beside it.
    source_id: str

    def calculate_markup_micros(self, provider_cost_micros: int) -> int:
        # Rounding is half-up on the micro, matching TenantMarkup exactly —
        # changing it would silently re-price every event.
        percent = (
            provider_cost_micros * self.markup_micro_percent + 50_000_000
        ) // 100_000_000
        return percent + self.fixed_uplift_micros

    def applied_to(self, provider_cost_micros: int) -> int:
        """The customer price this rung answers over a basis it is given.

        The basis plus the markup taken on it, said once. It is a method rather
        than two lines at the resolver because the cache's whole contract is
        that it answers what a live resolve answers, and a sum written at each
        caller is how two callers come to disagree about what "marked up" meant.

        The caller decides whether a basis may be marked up at all: an
        `unresolved` cost is `waived` and never arrives here, and a resolved
        zero IS a basis — a call that genuinely cost nothing, marked up to the
        uplift.
        """
        return provider_cost_micros + self.calculate_markup_micros(
            provider_cost_micros)

    def as_provenance(self):
        """The rung and the record, for the receipt's cross-reference section.

        Written here rather than at the writer because it is the value object's
        own statement of where it came from, and because `provenance` carries
        ids only — assembling it beside the terms is how a figure ends up in a
        section whose whole job is to hold none.
        """
        return {"rung": self.source, "record_id": self.source_id}


def _from_the_customer_override(row):
    """The customer's own markup — a row of the record #369 deletes."""
    return ResolvedMarkup(
        markup_micro_percent=row.markup_percentage_micros,
        fixed_uplift_micros=row.fixed_uplift_micros,
        source=MARKUP_RUNG_CUSTOMER,
        source_id=str(row.id),
    )


class MarkupService:
    @staticmethod
    def resolve(tenant, customer):
        """Return the applicable ResolvedMarkup, or None if nothing applies.

        `None` is not a price and never has been a zero: a tenant that has
        declared no rung has said nothing about what to charge, and what
        resolution makes of that is `unknown` (`pricing_service`).
        """
        if customer is not None:
            override = TenantMarkup.objects.filter(
                tenant=tenant, customer=customer).first()
            if override:
                return _from_the_customer_override(override)

            from apps.platform.plans.queries import get_plan_markup_for_customer
            plan_markup = get_plan_markup_for_customer(tenant.id, customer.id)
            if plan_markup is not None:
                return ResolvedMarkup(
                    markup_micro_percent=plan_markup[
                        "markup_percentage_micros"],
                    fixed_uplift_micros=plan_markup["fixed_uplift_micros"],
                    source=MARKUP_RUNG_PLAN,
                    source_id=str(plan_markup["plan_id"]),
                )

        declared = TenantDefaultMarkup.objects.filter(tenant=tenant).first()
        if declared:
            # NO UPLIFT ON THIS RUNG, AND NOT BECAUSE THE COLUMN WAS FORGOTTEN.
            # A rule that takes a margin over cost does not also carry a flat
            # addend (#147 §2) — non-composition is what makes a resolved price
            # explicable by naming one thing — so the replacement rung was built
            # without one, and the zero here is the arithmetic saying so rather
            # than a value read from anywhere.
            return ResolvedMarkup(
                markup_micro_percent=declared.markup_micro_percent,
                fixed_uplift_micros=0,
                source=MARKUP_RUNG_TENANT_DEFAULT,
                source_id=str(declared.id),
            )
        return None

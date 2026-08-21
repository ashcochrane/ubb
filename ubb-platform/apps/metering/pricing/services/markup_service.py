"""Markup resolution — the last rung of the price ladder.

**ONE RUNG, DECLARED BY THE TENANT (#357, #369).** Where the books in play hold
no rule for a quantity, the customer's price is a percentage over what UBB knows
the call cost. The tenant declares that percentage once, on
:class:`~apps.metering.pricing.models.TenantDefaultMarkup`, and this module
resolves it.

Precedence used to read

    customer override -> customer's Plan -> the tenant's declared default -> none

and #369 deleted the first two rungs with the records they read. Neither
disappeared as a capability: a customer's own price is a rule in the customer's
own Pricing Book (#361), and a plan's is a rule in the book the plan names
(#362). Both are resolved by the rate ladder ABOVE this module, on records that
say which quantity they price. What was deleted is a *percentage on a
configuration row* — a number that could not say what it applied to, and whose
only account of itself on a receipt was its own value.

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

**THE RUNG IS DECLARED, NOT INFERRED FROM AN ABSENCE (#357).** It used to be the
`customer IS NULL` row of the per-customer table — the tenant default by being
the one row with no customer on it. It is now its own declared record, with its
own routes and its own two audit actions, and a tenant who has declared nothing
has NO rung: resolution answers `unknown` rather than zero.
"""
from dataclasses import dataclass

from apps.metering.pricing.models import TenantDefaultMarkup

#: WHICH RUNG SUPPLIED A PERCENTAGE — the value the receipt's provenance names.
#:
#: A named constant rather than a string literal because the receipt records it,
#: so it is part of what a stored record means rather than an implementation
#: detail of this module.
#:
#: ⚠ **ONE VALUE, AND RECEIPTS WRITTEN BEFORE #369 CARRY TWO MORE.** The
#: customer-override and plan rungs each named themselves here, and the records
#: they read are deleted, so nothing writes those words again — but they are on
#: postings already, in a `provenance` section whose whole job is to survive the
#: configuration it points at. Nothing reads the value back by constant, which
#: is why the two are deleted here rather than kept as unwritable spellings.
#:
#: **NOT A REGISTRY CONCEPT.** It crosses no typed surface — the receipt is
#: published as an untyped record — so nothing advertises it to a consumer who
#: could switch on it, and a single-member closed concept would be a value set
#: with nothing to discriminate.
MARKUP_RUNG_TENANT_DEFAULT = "tenant_default"


@dataclass(frozen=True)
class ResolvedMarkup:
    """The markup that applies to one tenant, and where it came from.

    Frozen: instances are shared through the L1 cache and must never be mutated
    by a caller. ``source`` and ``source_id`` are carried for provenance — they
    answer "why was this event priced this way" without re-deriving the chain,
    and the receipt records both beside the percentage itself.
    """
    #: Millionths of a percent: 1_000_000 is 1%. Spelled the way the record it
    #: is read from spells it, and not under the money suffix — `_micros` means
    #: millionths of a CURRENCY unit.
    markup_micro_percent: int
    #: Which rung answered. One rung exists, and the field is kept because the
    #: receipt names it: a record that says only "a margin was taken" is the
    #: record this programme exists to delete.
    source: str
    #: The id of the record the percentage was read from, as a string. A
    #: cross-reference and never a term: the record it names can be edited or
    #: withdrawn, which is exactly why the percentage travels by value beside it.
    source_id: str

    def calculate_markup_micros(self, provider_cost_micros: int) -> int:
        """The margin itself, over a basis this rung has been given.

        Rounding is half-up on the micro, unchanged from the record this rung
        replaced — changing it would silently re-price every event.

        ⚠ **THERE IS NO SECOND TERM (#147 §2, #369).** A flat per-event addend
        used to be added here, because the customer-override record and the plan
        catalog both carried one. Both are deleted, and a rule that takes a
        margin over cost does not also carry an addend, a floor or a cap: that
        is what makes a resolved price explicable by naming one thing.
        """
        return (
            provider_cost_micros * self.markup_micro_percent + 50_000_000
        ) // 100_000_000

    def applied_to(self, provider_cost_micros: int) -> int:
        """The customer price this rung answers over a basis it is given.

        The basis plus the markup taken on it, said once. It is a method rather
        than two lines at the resolver because the cache's whole contract is
        that it answers what a live resolve answers, and a sum written at each
        caller is how two callers come to disagree about what "marked up" meant.

        The caller decides whether a basis may be marked up at all: an
        `unresolved` cost is `waived` and never arrives here, and a resolved
        zero IS a basis — a call that genuinely cost nothing, marked up to
        nothing.
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


class MarkupService:
    @staticmethod
    def resolve(tenant):
        """Return the tenant's declared markup rung, or None if they have none.

        `None` is not a price and never has been a zero: a tenant that has
        declared no rung has said nothing about what to charge, and what
        resolution makes of that is `unknown` (`pricing_service`).

        ⚠ **THE CUSTOMER IS NOT AN ARGUMENT, AND THAT IS THE SHAPE OF THE
        LADDER RATHER THAN AN OMISSION (#369).** Two rungs above this one read a
        customer — their own override row and their plan's percentage — and both
        records are deleted. What one named customer is charged is decided
        further up the ladder, by a rule in their own Pricing Book, on a record
        that says which quantity it prices. A customer argument here would be an
        argument that cannot change the answer, and a caller would read it as
        evidence that a per-customer markup still resolves.
        """
        declared = TenantDefaultMarkup.objects.filter(tenant=tenant).first()
        if declared is None:
            return None
        return ResolvedMarkup(
            markup_micro_percent=declared.markup_micro_percent,
            source=MARKUP_RUNG_TENANT_DEFAULT,
            source_id=str(declared.id),
        )

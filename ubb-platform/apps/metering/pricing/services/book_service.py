from django.db import transaction
from django.utils import timezone

from apps.metering.pricing.models import PRICING_MODEL_CHOICES, Rate, RateCard

_RATE_COPY_FIELDS = (
    "tenant_id", "customer_id", "card_type", "provider", "event_type",
    "task_type", "subtask_type",
    *(f"grouping_field_{i}" for i in range(1, 11)),
    # The REFERENCE, not the name (#326). A reprice copies which declaration the
    # outgoing rate priced; it never re-resolves the name, so a publish cannot
    # quietly move a rate onto a different declaration between versions.
    "measurement_id", "pricing_model", "rate_per_unit_micros",
    "unit_quantity", "fixed_micros", "currency",
    "lineage_id", "rate_card_id",
)


class BookService:
    @staticmethod
    def publish(book, changes, as_of=None):
        """Atomically reprice a set of the book's rates. Each change must match
        exactly one ACTIVE rate in the book by (measurement_key, plus the
        fourteen selector columns — provider, event_type, task_type,
        subtask_type and the ten slots). Only six of the slots can be pinned
        through the published reprice body — no slice-2 ticket widens it, and
        slice 4 rebuilds this entity's published surface — so a change body
        leaves the other four at "", and a rate pinned on one of them is not
        repriceable through this route.
        Supersedes it (valid_to=T, book_version_to=old
        version) and inserts a new active rate (same lineage_id, valid_from=T,
        book_version_from=new version). Bumps book.version once. All-or-nothing.

        ONE CLOCK CLOSES THE BOUNDARY AND OPENS IT, AND THAT FIXED A LIVE BUG
        (#325). Until the effective moment became suppliable, the replacement
        opened at the instant of INSERT — `T + ε`, strictly after the moment the
        outgoing rate closed at. Resolution asks for `valid_from <= as_of` and
        `valid_to > as_of`, so no rate at all covered `[T, T + ε)`: an event
        landing in that window matched nothing and fell through to markup
        pricing, which returns a plausible number and raises nothing.
        Microseconds wide, real and invisible. Both rows now take the same `T`,
        which with a half-open range is exactly no gap and exactly no overlap.
        `NoInstantFallsBetweenTwoVersionsTest` holds it.

        A FUTURE `as_of` IS NOW HONOURED DOWNSTREAM, AND THIS METHOD
        INVALIDATES NOTHING (#356). The two defects the pricing-versions
        decision (§8.3) assigned to the work that introduces forward-dating are
        both paid: `CardCache.resolve` takes the instant as a parameter instead
        of reading a clock, and its key carries that instant — so a cached
        resolution answers for the moment it was computed for and for no other.
        A publish therefore has nothing to invalidate. Entries for instants
        before the new boundary stay correct forever, and entries for instants
        after it were never created; the alternative, invalidating *at* the
        boundary, is the scheduled job forward-dated publishing exists to avoid,
        and "nothing runs at the effective instant" is only literally true
        without it.

        What this method still does not do is REFUSE a moment: nothing here
        advertises a future `as_of`, no caller passes one, and the published
        body carries no moment at all. This entity's published surface, and the
        horizon a forward-dated publish is bounded by, are the following
        tickets'.
        """
        as_of = as_of or timezone.now()
        with transaction.atomic():
            locked = RateCard.objects.select_for_update().get(id=book.id)
            new_version = locked.version + 1
            for ch in changes:
                # Matched on the NAME the change body carries, read through the
                # reference (#326) — a reprice body names a quantity, not a
                # declaration id, and nothing published gives a caller one to
                # name. A rate the conversion deactivated references nothing and
                # is therefore unmatchable here, which is the same answer it
                # gives resolution: it cannot be repriced, and the refusal below
                # says so with the name in it.
                #
                # `of=("self",)` locks the RATE and not the row it joins. The
                # lock is here to serialise reprices of one rate; a declaration
                # is read-only on this path, and locking it would make two
                # publishes of two different rates that happen to price one
                # quantity wait for each other.
                old = Rate.objects.select_for_update(of=("self",)).filter(
                    rate_card=locked, valid_to__isnull=True,
                    measurement__code=ch["measurement_key"],
                    **{s: ch.get(s, "") for s in Rate.SELECTORS},
                ).first()
                if old is None:
                    raise ValueError(
                        f"publish: no active rate for {ch['measurement_key']!r} in book {locked.key}")
                data = {f: getattr(old, f) for f in _RATE_COPY_FIELDS}
                for k in ("pricing_model", "rate_per_unit_micros", "unit_quantity",
                          "fixed_micros"):
                    if k in ch:
                        data[k] = ch[k]
                data["book_version_from"] = new_version
                data["book_version_to"] = None
                data["valid_from"] = as_of
                # Re-validate the repriced shape so a publish can never create a
                # rate with a retired/unknown pricing_model. Raises
                # ValueError -> rolls back the whole publish (endpoint maps 422).
                valid_models = {c[0] for c in PRICING_MODEL_CHOICES}
                if data["pricing_model"] not in valid_models:
                    raise ValueError(
                        f"pricing_model must be one of {sorted(valid_models)}")
                # Close the old row at T, then open the new AT THE SAME T.
                old.valid_to = as_of
                old.book_version_to = locked.version
                old.save(update_fields=["valid_to", "book_version_to", "updated_at"])
                Rate.objects.create(**data)
            locked.version = new_version
            locked.save(update_fields=["version", "updated_at"])
            book.version = new_version
            return book

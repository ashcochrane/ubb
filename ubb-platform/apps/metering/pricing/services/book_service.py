from django.db import transaction
from django.utils import timezone

from apps.metering.pricing.models import PRICING_MODEL_CHOICES, Rate, RateCard
from apps.metering.pricing.services.card_cache import CardCache

_RATE_COPY_FIELDS = (
    "tenant_id", "customer_id", "card_type", "provider", "event_type",
    "task_type", "subtask_type",
    *(f"grouping_field_{i}" for i in range(1, 11)),
    "measurement_key", "pricing_model", "rate_per_unit_micros",
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

        `as_of` IS STILL EXPECTED TO BE ~NOW, AND THAT IS A CONSTRAINT RATHER
        THAN A HABIT. The column stopped overwriting a supplied moment, so both
        rows here would faithfully take a future `as_of` — but faithfully
        writing a future boundary is not the same as honouring one, and two
        things downstream do not. `CardCache.resolve` hardcodes
        `timezone.now()` rather than the event's own instant, and this method
        invalidates that cache at publish time, which is the wrong moment when
        the boundary is in the future; the 2026-07-31 pricing-versions decision
        (§8.3) assigns both to the work that introduces forward-dating. So
        nothing here advertises a future `as_of`, no caller passes one, and the
        published body carries no moment at all — this entity's published
        surface is slice 4's.
        """
        as_of = as_of or timezone.now()
        with transaction.atomic():
            locked = RateCard.objects.select_for_update().get(id=book.id)
            new_version = locked.version + 1
            for ch in changes:
                old = Rate.objects.select_for_update().filter(
                    rate_card=locked, valid_to__isnull=True,
                    measurement_key=ch["measurement_key"],
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
            transaction.on_commit(lambda: CardCache.invalidate(locked.tenant_id))
            return book

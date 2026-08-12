import re

from django.db import IntegrityError, transaction

from apps.platform.grouping_fields.models import (
    FORBIDDEN_KEYS, RESERVED_KEYS, SLOT_CHOICES, GroupingField,
    GroupingFieldValue,
)

KEY_PATTERN = re.compile(r"[a-z][a-z0-9_]{1,63}")

#: The slots that exist, in declaration order. A stored slot IS a column name on
#: the posting — `admit` below returns `{slot: value}` and the recording path
#: hands that map to `create()` as keyword arguments — so a slot outside this
#: list is not a bad label, it is a declaration bound to a column that does not
#: exist, and every event the tenant records against it would fail at insert.
SLOTS = tuple(slot for slot, _ in SLOT_CHOICES)


class DimensionError(ValueError):
    """A declaration or value admission violated the registry's rules."""


class DimensionService:
    @staticmethod
    def declare(tenant, *, key, slot, scope, max_cardinality=100):
        """Declare or update one dimension. Idempotent on (key, slot, scope);
        enforces the D8 mutability rules."""
        if not KEY_PATTERN.fullmatch(key or ""):
            raise DimensionError(
                f"invalid dimension key {key!r}: must match [a-z][a-z0-9_]{{1,63}}")
        if key in RESERVED_KEYS:
            raise DimensionError(
                f"{key!r} is a reserved dimension — always present, never declared")
        if key in FORBIDDEN_KEYS:
            raise DimensionError(
                f"{key!r} is a correlation identifier, not a dimension: it is "
                "unbounded, so it is a filter parameter and cannot be grouped by")
        # #276 widened this vocabulary from six slots to ten AND re-spelled all
        # of them, so a caller written against the old spelling now names a slot
        # that does not exist.
        #
        # WITHOUT THIS LINE THAT CALLER GETS A 200 AND LOSES ITS DATA, SILENTLY.
        # The declaration stores; `admit` below then returns `{unknown: value}`;
        # and `_inherit_dimensions` copies only the slots it knows about, so the
        # value is dropped on the floor. Every event the tenant records against
        # that key is attributed to nothing, and the first sign of it is a chart
        # with a column missing. Refusing here turns that into a 422 against the
        # request that is actually wrong.
        if slot not in SLOTS:
            raise DimensionError(
                f"{slot!r} is not a slot: the slots are {', '.join(SLOTS)}")

        existing = GroupingField.objects.filter(tenant=tenant, key=key).first()
        if existing is None:
            # uq_dimension_def_slot is (tenant, slot) — a slot binds to ONE
            # key at a time, regardless of scope. Check for that collision
            # here (a different key already bound to this slot) so a
            # copy-paste mistake is a 422 DimensionError, not a raw
            # IntegrityError the endpoint doesn't catch (500).
            slot_holder = GroupingField.objects.filter(tenant=tenant, slot=slot).first()
            if slot_holder is not None:
                raise DimensionError(
                    f"slot {slot!r} is already bound to key {slot_holder.key!r}: "
                    f"cannot also bind {key!r} to it — a slot holds exactly one "
                    "key at a time")
            return GroupingField.objects.create(
                tenant=tenant, key=key, slot=slot, scope=scope,
                max_cardinality=max_cardinality)

        if existing.slot != slot:
            raise DimensionError(
                f"{key!r} slot is immutable: bound to {existing.slot}, cannot "
                f"rebind to {slot} — historical rows in that column would "
                "silently change meaning")
        if existing.scope != scope:
            raise DimensionError(
                f"{key!r} scope is immutable: declared {existing.scope}, cannot "
                f"change to {scope} — inheritance would differ between old and "
                "new rows")
        if max_cardinality < existing.max_cardinality:
            raise DimensionError(
                f"{key!r} max_cardinality cannot be lowered "
                f"({existing.max_cardinality} -> {max_cardinality})")
        if max_cardinality != existing.max_cardinality:
            existing.max_cardinality = max_cardinality
            existing.save(update_fields=["max_cardinality", "updated_at"])
        return existing

    @staticmethod
    def admit(tenant, values, scope):
        """Validate a {key: value} map for one scope and return {slot: value}.

        Records novel values in the GroupingFieldValue ledger, refusing any that
        would push a key past its cap (D4). The cap is a keyspace guard, not
        an invariant: concurrent novel values at the boundary may overshoot by
        the number of writers, which is harmless.

        The entire operation is atomic: if any key validation or cardinality
        check fails, no values are recorded.
        """
        values = values or {}
        if not values:
            return {}
        defs = {d.key: d for d in GroupingField.objects.filter(
            tenant=tenant, key__in=list(values))}
        out = {}
        with transaction.atomic():
            for key, raw in values.items():
                d = defs.get(key)
                if d is None:
                    raise DimensionError(f"unknown dimension {key!r}: declare it first")
                if d.scope != scope:
                    raise DimensionError(
                        f"{key!r} is declared at {d.scope} scope and cannot be set "
                        f"at {scope} scope")
                value = str(raw)
                if len(value) > 100:
                    raise DimensionError(
                        f"dimension {key!r} value exceeds 100 characters")
                DimensionService._record_value(tenant, d, value)
                out[d.slot] = value
        return out

    @staticmethod
    def _record_value(tenant, grouping_field, value):
        if GroupingFieldValue.objects.filter(
                tenant=tenant, key=grouping_field.key, value=value).exists():
            return
        if grouping_field.retired_at is not None:
            raise DimensionError(
                f"dimension {grouping_field.key!r} is retired and accepts no new "
                f"values (got {value!r})")
        count = GroupingFieldValue.objects.filter(
            tenant=tenant, key=grouping_field.key).count()
        if count >= grouping_field.max_cardinality:
            raise DimensionError(
                f"dimension {grouping_field.key!r} cardinality exceeded: "
                f"{count} distinct values already recorded (max "
                f"{grouping_field.max_cardinality}); {value!r} refused. High-"
                "cardinality data belongs in metadata or a filter, not a "
                "dimension")
        try:
            with transaction.atomic():
                GroupingFieldValue.objects.create(
                    tenant=tenant, key=grouping_field.key, value=value)
        except IntegrityError:
            # A concurrent writer admitted the same novel value — benign.
            pass

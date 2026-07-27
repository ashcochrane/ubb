import re

from django.db import IntegrityError, transaction

from apps.platform.dimensions.models import (
    FORBIDDEN_KEYS, RESERVED_KEYS, DimensionDef, DimensionValue,
)

KEY_PATTERN = re.compile(r"[a-z][a-z0-9_]{1,63}")


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

        existing = DimensionDef.objects.filter(tenant=tenant, key=key).first()
        if existing is None:
            return DimensionDef.objects.create(
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

        Records novel values in the DimensionValue ledger, refusing any that
        would push a key past its cap (D4). The cap is a keyspace guard, not
        an invariant: concurrent novel values at the boundary may overshoot by
        the number of writers, which is harmless.
        """
        values = values or {}
        if not values:
            return {}
        defs = {d.key: d for d in DimensionDef.objects.filter(
            tenant=tenant, key__in=list(values))}
        out = {}
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
    def _record_value(tenant, dimension_def, value):
        if DimensionValue.objects.filter(
                tenant=tenant, key=dimension_def.key, value=value).exists():
            return
        if dimension_def.retired_at is not None:
            raise DimensionError(
                f"dimension {dimension_def.key!r} is retired and accepts no new "
                f"values (got {value!r})")
        count = DimensionValue.objects.filter(
            tenant=tenant, key=dimension_def.key).count()
        if count >= dimension_def.max_cardinality:
            raise DimensionError(
                f"dimension {dimension_def.key!r} cardinality exceeded: "
                f"{count} distinct values already recorded (max "
                f"{dimension_def.max_cardinality}); {value!r} refused. High-"
                "cardinality data belongs in tags or a filter, not a dimension")
        try:
            with transaction.atomic():
                DimensionValue.objects.create(
                    tenant=tenant, key=dimension_def.key, value=value)
        except IntegrityError:
            # A concurrent writer admitted the same novel value — benign.
            pass

"""What the Code Builder stores: one immutable snapshot per resolved Blueprint.

**Why anything is stored at all.** A generated integration and the run that
verifies it must have seen exactly the same configuration, and a hash
recomputed at verification time from whatever configuration exists by then
cannot promise that. So resolving a Blueprint from published configuration
keeps the resolved content, and the content's own hash — its
``configuration_fingerprint`` — is what the generated code is stamped with
(#184 §13, the owner's watch-point of 2026-09-25).

**Why the kernel, when resolution is composition-layer work.** Resolution reads
the kernel's registries and metering's rules together, so it lives in
``api/v1`` (ADR-001 rule 4). What it leaves behind is plain data under a tenant
and imports no product, and a record needs an app to live in — which the
composition layer is not. ``snapshots.py`` next door is the whole of what may
be done with one.

**It is a derived test fixture, and each word of that is a constraint**
(#184 §2):

* *not tenant configuration* — nothing resolves, rates, prices or enforces from
  it, and no production path reads it;
* *not editable and not published* — it has no lifecycle, only an existence;
* *prunable* — it may be deleted at any time, by retention, by a sandbox reset
  or with its tenant, and a fingerprint whose snapshot is gone answers
  not-found, after which the developer resolves again.

**The fingerprint is not a catalogue-wide revision id.** It names the content
of one resolution of one selection. Two selections over the same configuration
are two snapshots, and nothing may read it as "the tenant's configuration at
revision N".
"""
from django.db import models

from core.models import BaseModel
from core.transitions import FROZEN

#: What every fingerprint begins with: the name of the hash that produced the
#: rest. Said on the value so a reader holding one, in a file header or a
#: route, knows what it is a hash by without being told.
FINGERPRINT_PREFIX = "sha256:"

#: A fingerprint in full — the prefix and the digest's 64 lowercase hex
#: characters. One pattern, read by the database check below and by the route
#: that is addressed by one.
FINGERPRINT_PATTERN = r"^sha256:[0-9a-f]{64}$"

FINGERPRINT_LENGTH = len(FINGERPRINT_PREFIX) + 64


class BlueprintSnapshot(BaseModel):
    """The resolved content of one Blueprint, addressed by its own hash.

    Content-addressed and idempotent: storing the same content for the same
    tenant twice is one row, which the uniqueness key below is what makes true
    rather than a lookup that could race.

    **Per tenant.** Two tenants whose configuration happens to resolve to the
    same content hold a row each under the same fingerprint, and neither can
    read the other's: the fingerprint identifies content, and the tenant is
    who it belongs to.
    """
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE,
                               related_name="blueprint_snapshots")
    configuration_fingerprint = models.CharField(max_length=FINGERPRINT_LENGTH)
    #: The canonical content the fingerprint is the hash of, exactly as
    #: `snapshots.fingerprint_of` read it.
    content = models.JSONField()

    #: WHAT MAY HAPPEN TO EACH COLUMN (ADR-0007 §2): nothing, after insert.
    #: A snapshot whose content could move would be a fingerprint naming
    #: something other than what a file was generated from. The rule that
    #: keeps it is a `BEFORE UPDATE` trigger on this table, installed by
    #: `code_builder/migrations/0001`.
    #:
    #: ⚠ DELETE IS DELIBERATELY NOT REFUSED. A snapshot is prunable, and a
    #: sandbox reset or a tenant's removal takes it by cascade — a refusal on
    #: delete cannot tell a prune from a cascade and would fail the whole reset.
    #:
    #: The tenant is declared as its COLUMN, because the walk that holds these
    #: declarations to the database searches a trigger body, and a trigger
    #: says `NEW.tenant_id`.
    transition_classes = {"tenant_id": FROZEN,
                          "configuration_fingerprint": FROZEN,
                          "content": FROZEN}

    class Meta:
        db_table = "ubb_blueprint_snapshot"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "configuration_fingerprint"],
                name="uq_blueprint_snapshot_fingerprint"),
            models.CheckConstraint(
                condition=models.Q(
                    configuration_fingerprint__regex=FINGERPRINT_PATTERN),
                name="ck_blueprint_snapshot_fingerprint_shape"),
        ]

    def __str__(self):
        return f"BlueprintSnapshot({self.configuration_fingerprint})"

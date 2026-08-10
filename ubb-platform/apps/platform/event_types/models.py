"""The tenant's Event Type catalogue — the vocabulary UBB meters against.

An Event Type is the aggregate root a tenant registers: what it is called, the
quantities it declares, which of those drive cost, and how that cost is arrived
at. The supplier it came from, the category it groups under and the declared
quantities themselves all live here too, so the app name under-describes its own
contents. That is deliberate (spec §A1): "catalogue" already means two other
things in live prose — the webhook catalogue and the label catalogue — so the app
takes the name of the thing everything else hangs off rather than a word a reader
would have to disambiguate.

**Why this is not the app next door.** ``apps.platform.events`` is the
event-*delivery* app: the outbox, the handler checkpoints, dispatch, the webhook
catalogue and announcements. Its ``event_type`` is a webhook name such as
``usage.recorded`` — a UBB-owned notification, not a tenant-declared metered
call. Putting the tenant's metered vocabulary beside it would reproduce
ADR-0006's opening complaint, one word carrying two meanings, inside the kernel's
most-read module. ADR-0006 §7 is the rule that settles it: where infrastructure's
word collides with a domain word the infrastructure yields, and slice 0 made
exactly this move for exactly this reason when it took the platform's unit of
work out from under a framework noun.

**Why the kernel and not metering** (ADR-001): rating reads this catalogue, the
drawdown reads its cost, analytics groups by it, the Code Builder reads it, and
the spend-ceiling work needs it in order to know *in advance* that the events it
governs are costable. Three or more products means ``apps/platform/``.

**Why this module is empty.** It declares no model yet, and it exists anyway
because ``domain-vocabulary/`` names it as the end-state backend consumer for
the concepts whose values the entities here will hold by reference — and the
registry compiler refuses a declared consumer path that does not exist. So the
module lands before the models that fill it, and the recorded consumer debts
naming this path stay open until the fields that serve them are built. The
entities arrive in the tickets that follow.
"""

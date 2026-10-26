"""Replay consumers: the kernel hands each remediation's ``Replay`` to whichever
product asked, inside the remediation's own transaction (#473 row 1, #568) —
the platform-hooks channel of ADR-001 rule 3, on the shape of
`apps/platform/work/hooks.py`.

WHY A REGISTRY, AND NOT AN IMPORT OR AN OUTBOX EVENT. A remediation is a kernel
act — the tenant says what a held name meant — and what it entitles is a
product's: the event is re-costed and re-priced from its original moment, and
the posting that holds it is metering's. The kernel may not import a product
(ADR-001 rule 2). Every outbox event is a published webhook, so routing this
through one would put an internal re-costing on the tenant contract; and it
would make the replay asynchronous, so a period could close between the tenant's
decision and the cost it entitles. So a product registers a consumer in its
`AppConfig.ready()`, and :func:`hand_on` calls every consumer synchronously at
the remediation, in registration order. Registration is idempotent because
`ready()` can run more than once, and no products installed means no consumers
means a no-op.

⚠ **A CONSUMER THAT RAISES VETOES THE REMEDIATION — THE DELIBERATE OPPOSITE OF
THE WORK REGISTRY.** There, a listener is a notification about a kernel fact
already true, and a product's bug must not undo a unit of work's end. Here the
replay IS the decision's consequence: a held name recorded as mapped whose event
was never re-costed has left the period-close safeguard while the posting stays
uncosted, and nothing would ever look at it again. So nothing here catches, and
the remediation (`quarantine._remediate`) runs inside one transaction with the
consumers: either the decision and its replay both land, or neither does.
The one carve is the caller's, not this module's: the answering a publication
sets going once it has committed (`quarantine.answer_what_publications_
declare`) gives each held name a transaction of its own, so a name a consumer
refuses or breaks on stays held while the names beside it are answered — and
the publication, already committed, is never what is vetoed.

Nothing in this module reads or writes a row of its own.
"""

_consumers = []


def register_replay_consumer(fn):
    """Register ``fn(replay)`` to run on every remediation that names a
    declaration. Idempotent (AppConfig.ready() can run more than once)."""
    if fn not in _consumers:
        _consumers.append(fn)


def hand_on(replay):
    """Invoke every registered consumer synchronously, in registration order,
    with the ``Replay`` a remediation has just entitled.

    Called inside the remediation's transaction; an exception propagates and
    takes the remediation with it — see the module docstring for why.
    """
    for fn in _consumers:
        fn(replay)

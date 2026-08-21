"""The audit action registry — the contractual vocabulary of recordable actions.

Each recorded action is a stable, domain-shaped name (``noun.verb``) that is part
of the public compatibility contract (ADR-004 §2, under ADR-003's rules):
**additive-only, a rename is a breaking change**. Names are deliberately decoupled
from routes — the ADR-002 single-API restructure renames routes; it must never
rewrite history's vocabulary — and equally decoupled from the webhook catalog
(``apps/platform/events/catalog.py``): queue and ledger stay separate concepts, so
the audit action ``api_key.created`` and the webhook event ``tenant.api_key_created``
are independent names in independent contracts.

This is the audit twin of that catalog and the #63 error-code registry: one source
of truth, extended only by appending. ``record()`` refuses an unregistered name, so
the registry cannot silently drift from what the ledger actually writes — and the
#82 mutating-route CI pin checks new routes against exactly this set.
"""

# Order is not significant — grouped by namespace for readability. #81 landed the
# ledger and one real site (api-key mint); #82 sweeps the rest of the mutating
# surface in, appending here. Every name below is written by exactly one route (a
# few — budget.set, top_up.requested — by the tenant/customer or
# tenant/widget twins of one operation). Usage ingestion (record_usage[/batch],
# ingest, task close) and the spend pre-check are telemetry, not governance, and
# deliberately have NO action here — see the exemption list in
# api/v1/tests/test_audit_sweep.py.
AUDIT_ACTIONS = (
    # api keys / credentials (membership + key lifecycle)
    "api_key.created",
    "api_key.rotated",
    "api_key.revoked",
    # members & invitations (identity, #79/#80)
    "invitation.created",
    "invitation.revoked",
    "member.role_changed",
    "member.removed",
    # tenant governance / config
    "tenant.config_changed",
    "sandbox.created",
    "sandbox.reset",
    "connect.started",
    # spend-control config
    "budget.set",
    "billing_profile.set",
    "auto_top_up.configured",
    "postpaid_config.set",
    # hand-moved money
    "wallet.credited",
    "wallet.debited",
    "wallet.withdrawn",
    # A top-up is recorded at INITIATION (a pending attempt) — the crediting is
    # system-driven and lands later via the PaymentIntent path — so the name
    # says "requested", not "topped_up".
    "top_up.requested",
    "usage.refunded",
    "grant.created",
    "grant.voided",
    # THE BOOKS — DECLARING ONE AND WITHDRAWING ONE, PER KIND OF BOOK (#368,
    # spec §1, §19).
    #
    # ⚠ **THE LAST THREE NAMES OF THE OLD BLOCK LEFT HERE AND NONE WAS
    # RENAMED.** #367 took two of the seven; these are the remaining three, and
    # the acts they recorded have ceased to exist:
    #
    #   * *a book was created* — there is no such entity any more. The
    #     container split into a Pricing Book and a cost book, two separately
    #     shaped records, and they are DECLARED SEPARATELY below;
    #   * *a book was assigned to a customer* — the record that assigned one is
    #     deleted, and a customer reaches a book through their Plan (#362);
    #   * *a book was published* — the route that wrote it repriced a book
    #     immediately, with no record a tenant could read first. Every change
    #     to a book is a publish now, and `pricing_book_publish.published`
    #     below already records that act on the record that IS published. The
    #     old name could also mean either half of the discriminated entity,
    #     which is the second reason it has no successor.
    #
    # **Deleting an action whose act no longer exists is not the rename ADR-004
    # §2 governs.** A rename carries an act forward under a new spelling and
    # breaks a reader watching for the old one; these three have no successor
    # to carry forward.
    #
    # **NO PART OF THE ONE-TIME PRE-PRODUCTION AUDIT-REGISTRY RESET IS SPENT ON
    # THEM.** #154 §4.2 defines that exception and #154 §13 / #155 §14 allocate
    # it to slice 8, for the actions that genuinely ARE renamed. This deletion
    # needs none of it and must not be read as drawing against it.
    #
    # The mechanism is what makes it safe rather than merely defensible:
    # `record()` refuses an unregistered name, so an action deleted while a
    # route still wrote it would fail loudly — route and registry are forced
    # into one commit and there is no window in which a dead action is written.
    # The refusal is held for all three in
    # `apps/metering/pricing/tests/test_a_book_of_costs_and_a_book_of_prices_
    # are_two_shapes.py`, which composes the three names from a prefix it
    # derives rather than spelling them — a new module writing them would put
    # their ledger counts over entries that reach zero here. The ROUTER half —
    # which routes write the four names below, and that none of them takes the
    # audit sweep's exemption — is `api/v1/tests/test_the_book_acts_that_
    # ceased.py`.
    #
    # ⚠ **FOUR NAMES ARRIVE WHERE THE TICKET SAID TWO, AND THE ARITHMETIC IS
    # THE REGISTRY'S OWN RULE RATHER THAN A WIDENING.** The rule stated below —
    # one action per record per kind of act, *"split now, when it is free"* —
    # is what the ticket cites, and this commit creates TWO records: a Pricing
    # Book and a cost book have different columns, different products gating
    # them (a cost book is metering; a Pricing Book is billing) and different
    # readers. The ticket names two ACTS, declaring and withdrawing, and both
    # apply to both records. A shared noun would be the first place in this
    # registry where one action spans two record types, and it would put a
    # governance reader asking *"when did this tenant withdraw a PRICING
    # book"* back to reading `resource_type` — which is the thing the rule
    # below refuses. Splitting later is the rename ADR-004 §2 calls a breaking
    # change, and it is free exactly now.
    #
    # DECLARING AND WITHDRAWING ARE SPLIT for the reason every pair here is:
    # a correction to a declared book is still a declaration, and a reader
    # asking when a book stopped existing must not read metadata to find out.
    "pricing_book.declared",
    "pricing_book.withdrawn",
    "cost_book.declared",
    "cost_book.withdrawn",
    # ⚠ **THE LAST TWO RETIRED NAMES OF THE OLD BLOCK LEFT HERE, AND NEITHER
    # WAS RENAMED (#369).** They recorded that a tenant had set a markup and
    # that one had been removed — acts on a configuration record whose rows
    # were a percentage for the whole tenant and a percentage for one named
    # customer. **That record is deleted**, with its five routes and its two
    # schemas, and neither act has a successor to carry forward: a customer's
    # own price is a rule in their own Pricing Book, declared and withdrawn
    # under the pair further down; the tenant default is declared and withdrawn
    # under the pair below.
    #
    # **Deleting an action whose act no longer exists is not the rename ADR-004
    # §2 governs**, and **no part of the one-time pre-production audit-registry
    # reset is spent on it** — #154 §4.2 defines that exception and #154 §13 /
    # #155 §14 allocate it to slice 8, for the actions that genuinely ARE
    # renamed. The names are not spelled anywhere in this tree outside the
    # registry's own retired-alias list and the migrations, and the refusal is
    # held in `apps/metering/pricing/tests/test_the_markup_record_is_deleted
    # .py`, which derives the noun from the deleting migration's own from-state
    # rather than writing it.
    # THE TENANT'S DEFAULT MARKUP RUNG (#357). The last rung of the price
    # ladder — what a customer is charged where the tenant has written no rule
    # — so declaring it and withdrawing it are governance in exactly the sense
    # the pairs above are, and they take names rather than the exemption list.
    #
    # DECLARATION AND WITHDRAWAL ARE SPLIT, under the rule stated below: a
    # correction to a declared percentage is still a declaration, and a
    # governance reader asking "when did this tenant stop having a markup at
    # all" must not have to read metadata to find out — the two answers are
    # different acts. Splitting them later is the rename ADR-004 §2 calls a
    # breaking change, so they are split now, when it is free.
    #
    # ⚠ NOT A RENAME OF THE PAIR THAT USED TO SIT ABOVE. Those two recorded
    # acts on the record this rung replaces; #369 deleted that record and both
    # names with it, and the two sets were live at once in between because the
    # old record was still written. No part of the one-time pre-production
    # audit-registry reset was spent on either pair.
    "tenant_default_markup.declared",
    "tenant_default_markup.withdrawn",
    # CHANGING A PRICING BOOK (#358). Every change to a book is a publish —
    # adding a rule, repricing one and retiring one are one act, recorded once,
    # with a diff the tenant reads before committing to it. That collapse is
    # about the book's MUTATION surface; it is not an argument for collapsing
    # governance, and these three are three answers to three different
    # questions:
    #
    #   * a draft was declared — an intention, which closes nothing and writes
    #     no rule;
    #   * it was published — the act that closes each superseded rule and opens
    #     its replacement, and therefore the one that changes what a customer
    #     is charged;
    #   * it was discarded — an intention abandoned, leaving the book exactly
    #     as it stood.
    #
    # Reading which of the three happened out of an entry's metadata is what
    # the rule below refuses, and splitting them later is the rename ADR-004 §2
    # calls a breaking change; they are split now, when it is free.
    #
    # The noun is the publish record and not the book, because the ledger's
    # `resource_type` already says which record moved — the same reason the
    # Event Type's satellites each carry their own noun rather than borrowing
    # its.
    "pricing_book_publish.declared",
    "pricing_book_publish.published",
    "pricing_book_publish.discarded",
    # A CUSTOMER'S OWN PRICING RULE (#361, #151 §6). A tenant honouring a
    # negotiated deal gives one customer a rule that replaces what they
    # inherit — the whole rule, method included — and takes it away again when
    # the deal ends. Both are governance in the sense every pair above is:
    # they decide what one named customer is charged.
    #
    # DECLARING AND WITHDRAWING ARE SPLIT, under the rule the pairs above
    # follow. A governance reader asking "when did this customer stop having
    # their own price" must not have to read metadata to find out, and
    # splitting them later is the rename ADR-004 §2 calls a breaking change.
    #
    # ⚠ NOT `customer_pricing_override.set`, WHICH IS ALREADY IN THE REGISTRY
    # AND IS A DIFFERENT ACT. That name is the end-state spelling of the retired
    # setting action deleted above — a NUMBER written onto the per-customer row
    # of the record this slice deleted. An override is not a number inside a
    # rule; it is a whole rule, declared through a publish. Two acts on two
    # records, so two names, and neither is a rename of the other.
    #
    # ⚠ THE ACTS RECORD THE DRAFT, NOT THE RULE, WHICH IS WHY BOTH SIT BESIDE
    # THE THREE ABOVE. Declaring an override writes no rule: it declares a
    # change on the customer's own book, and publishing that change is what
    # puts the deal in force and is recorded under `pricing_book_publish.
    # published`. The `resource_type` is the publish record's for the same
    # reason theirs is — the ledger already says which record moved.
    "customer_pricing_override.declared",
    "customer_pricing_override.withdrawn",
    # EXECUTING A RESOLUTION RUN (#363, spec §10). The one recovery mechanism:
    # it completes fields a posting recorded as unresolved — a supplier cost
    # UBB never learned, a customer price no rule was written for — and moves
    # no money.
    #
    # Governance rather than telemetry, and by some distance the strongest
    # case in this registry for a name: a run writes money-adjacent numbers
    # into periods whose reporting is closed, it is authorised at the ADMIN
    # floor, and under the receipt's sealing rule it is IRREVERSIBLE. There is
    # no second act to undo one with, so the ledger entry is the only place
    # the actor and the selector survive.
    #
    # ⚠ ONE NAME RATHER THAN THE PAIR EVERY NEIGHBOUR ABOVE TAKES, and that is
    # this act's shape rather than a split deferred. Those pairs separate
    # declaring from withdrawing because both acts exist and a governance
    # reader must not read metadata to tell them apart. A run has no
    # withdrawal: its write is a one-time completion, after which the receipt
    # is sealed. Reserving a name for an act that cannot happen would be a
    # registry entry nothing may ever write.
    "resolution_run.executed",
    # Grouping Field registry (the 2026-07-27 unified grouping model plan under
    # `docs/plans/`, D1). Renamed with
    # the thing it records (#277): `audit_action` in
    # `domain-vocabulary/concepts/governance.yaml` carries the old name as a
    # retired alias and the canonical one in its values, so this is the ledger
    # taking the vocabulary the registry already declared for it.
    #
    # ADR-004 §2 makes these names additive-only and a rename a breaking
    # change; #154 §4.2 spends a one-time, scoped, pre-production exception on
    # exactly this name among others, and that exception is what this rename
    # is drawn against. It is spent at the cutover, not before.
    "grouping_field.declared",
    # task type registry (the same plan, D7)
    "task_type.declared",
    # The Event Type catalogue — what the tenant declares it meters (#267).
    # Declaring what a call is, and what it costs, is governance in the same
    # sense the two registries above are: it decides how usage is costed.
    #
    # ONE ACTION PER RECORD PER KIND OF ACT, which is the shape the pairs above
    # already run (`webhook_config.created`/`.deleted`, `grant.created`/
    # `.voided`, `pricing_book.declared`/`.withdrawn`). Declaring and
    # re-declaring are one act — a correction to a declaration is still a
    # declaration, which is
    # why `grouping_field.declared` covers a re-PUT — but WITHDRAWING is not, and
    # neither is publishing:
    #
    #   * publication is what a tenant's generated integration is built
    #     against, so "a draft was edited" and "revision 3 was published" are
    #     different answers to the question this ledger exists to answer;
    #   * a withdrawal removes something the tenant may be metering against,
    #     and a governance reader asking "when did this stop being declared"
    #     must not have to read metadata to find out;
    #   * retiring a supplier is a commercial decision to stop offering it,
    #     not a correction to its name.
    #
    # Splitting any of these later is the rename ADR-004 §2 calls a breaking
    # change, so they are split now, when it is free.
    "event_type.declared",
    "event_type.published",
    "measurement.declared",
    "measurement.withdrawn",
    "reported_cost_mapping.declared",
    "reported_cost_mapping.withdrawn",
    "provider.declared",
    "provider.retired",
    "event_category.declared",
    "event_category.withdrawn",
    # margin / revenue
    "margin_threshold.set",
    "revenue_profile.set",
    "revenue_mode.set",
    # customers & subscriptions
    "customer.created",
    "plan.created",
    "plan.updated",
    "plan.archived",
    "plan.assigned",
    "subscription.created",
    "subscription.canceled",
    "subscription.paused",
    "subscription.resumed",
    "subscription.seats_changed",
    # referrals
    "referral_program.created",
    "referral_program.updated",
    "referral_program.deactivated",
    "referral_program.reactivated",
    "referrer.registered",
    "referral.attributed",
    "referral.revoked",
    # webhook configuration
    "webhook_config.created",
    "webhook_config.updated",
    "webhook_config.deleted",
    "webhook_config.secret_rotated",
)

_AUDIT_ACTIONS_SET = frozenset(AUDIT_ACTIONS)


def is_registered_action(name):
    """True if ``name`` is a registered audit action."""
    return name in _AUDIT_ACTIONS_SET

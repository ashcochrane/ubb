"""What a delivered piece of work sold at one agreed price is owed for (#416,
spec §11).

**THE RULE IS HERE AND ONLY THE DIALECT IS IN THE ROUTE.** Whether a close earns
a charge, what that charge carries and how a wrong one is corrected are facts
about the concept, so they are decided in the product; rendering
`charge_created` on a response is the composition layer's job and belongs
nowhere else (`docs/conventions/django-patterns.md` §API, and #409's own
sentence, which #414 was graded against).

**WHY THIS LIVES IN `pricing` AND NOT IN `billing`.** A Charge is offered to
BOTH postures and means something different in each: for a tenant that bills
through UBB it is a real billable record like any other, and for one that does
not it is a recorded revenue and margin fact. A module inside a product a
metering-only tenant does not have could not produce the second, and the second
is the half no gate in this repository could ever ask for — a slice that built
only the billing reading would leave every board green. It sits beside the line
that priced it, whose book version and identity it carries, and beside the
receipt module that will explain it (#418).

⚠ **THE KERNEL DOES NOT CALL THIS AND MUST NOT.** `apps.platform.work` owns the
close and may not import a product (ADR-001), so the composition layer is what
puts the two together — exactly as it already does for the start gate, where
`api/v1/task_endpoints.py` resolves the agreed price out of this same app and
hands it to `TaskService.create_task`. The alternative, an outbox event, was not
taken: a charge must be written in the SAME transaction as the transition that
earns it, or a crash between them loses revenue for delivered work with nothing
to replay from.
"""
from django.utils import timezone

from apps.metering.pricing.models import Charge
from core.money import DEFAULT_CURRENCY
from core.vocabulary import TASK_STATUS_COMPLETED

#: The prefix a derived key carries, so a reader meeting one in a money system
#: can tell what produced it without a join. Spelled once, here, rather than at
#: each call site — #413 paid for a key constant defeated by its own tests
#: spelling the literal one file away.
KEY_PREFIX = "task"


def derived_key(task_id, *, correction=None):
    """The exactly-once key for a charge against ``task_id``.

    DERIVED, NEVER CALLER-SUPPLIED (spec §11). A piece of work already has a
    unique identity within its tenant and customer, and letting a caller name
    the key would put the one thing that makes a charge exactly-once into the
    hands of the party retrying the request.

    ``correction`` numbers a compensating record so that a piece of work
    corrected twice does not collide with itself. It is a plain ordinal rather
    than a second identifier because the trail is READ in order, and an ordinal
    is what says which correction came second.
    """
    key = f"{KEY_PREFIX}:{task_id}"
    return key if correction is None else f"{key}:correction:{correction}"


def charge_for_delivered_work(task):
    """The Charge a delivered piece of work earns, or ``None`` where none is.

    **CALL THIS ONLY ON THE WINNING TRANSITION INTO THE DELIVERED STATE.**
    `TaskService._flip` returns which call performed the flip out of `active`,
    and that is the exactly-once trigger #409 built the close around. This
    function asserts the STATE for itself rather than trusting the caller to
    have asked — the two together are belt and braces, and the partial
    uniqueness on `ubb_charge` is the third — but it cannot see the race on its
    own, so the caller's guard is not redundant.

    **WHAT DECIDES THAT A CHARGE IS OWED IS THE PINNED PRICE, AND NOTHING
    ELSE.** A non-null `agreed_price_micros` already means everything a longer
    condition would have to re-check: `ck_task_agreed_price_only_on_a_whole_
    fixed_unit` admits one only on a WHOLE piece of work sold at one agreed
    price, so contained work and work priced per event both fall out here with
    no second reading of the regime — and a second reading is exactly where two
    conditions get the chance to disagree.

    ⚠ **THE POSTURE IS NOT ASKED AND THAT IS DELIBERATE.** #415's start gate
    conditions ONE refusal on whether the tenant bills through UBB, because
    refusing their work over a pricing gap would refuse it over revenue nobody
    collects. Nothing of that transfers here: a price that resolved was pinned
    for them precisely so their margin reporting has a revenue number in it, and
    this row is that number's canonical record. A posture condition here would
    be the defect the ticket names — building the billing half only — and it
    would leave every gate green.

    Must be called inside @transaction.atomic, with the transition it belongs
    to.
    """
    if task.status != TASK_STATUS_COMPLETED:
        return None
    if task.agreed_price_micros is None:
        return None
    return Charge.objects.create(
        tenant_id=task.tenant_id,
        task=task,
        amount_micros=task.agreed_price_micros,
        currency=(task.tenant.default_currency or DEFAULT_CURRENCY).lower(),
        # COPIED OFF THE WORK, WHICH PINNED BOTH AT RESOLUTION (#415). Neither
        # is re-derived and neither could be — #139 §2.3 forbids re-resolving
        # today's configuration to explain yesterday's amount.
        agreed_price_line_id=task.agreed_price_line_id,
        book_version=task.agreed_price_book_version,
        # THE START INSTANT AND THE DELIVERY INSTANT, in that order. The second
        # is the one the winning transition wrote, so every projection of this
        # Charge carries the same instant rather than its own reading of "now".
        resolved_at=task.created_at,
        charged_at=task.completed_at,
        idempotency_key=derived_key(task.id),
        **_the_grouping_values_on(task))


def compensate(charge, *, note):
    """Correct ``charge`` by writing the record that reverses it.

    **THE ONLY CORRECTION THERE IS, BECAUSE THE COLUMNS ARE FROZEN.** ADR-0007
    §2's `FROZEN` class is held on `ubb_charge` by a trigger, so a wrong charge
    cannot be rewritten through any door; what it can be is superseded by a row
    naming it. The original still says what UBB originally charged — which is
    the property an edit destroys and the reason a wrong number here leaves a
    trail instead of vanishing.

    A REVERSAL RATHER THAN A REPLACEMENT, and re-stating a corrected number is a
    second call to this function with the difference. Reversal is the primitive
    because it is the one that is always right: netting an original against its
    negation is arithmetic no reader has to interpret, whereas a "replace with"
    row would need every reader to know which of two numbers was live.

    ⚠ **THE SUBJECT COMES FROM THE ORIGINAL AND IS NEVER PASSED IN.** A
    correction naming a different piece of work than the charge it corrects would
    be unreadable as a trail and is not expressible at the database — the rule
    reads two rows, which no `CHECK` can do — so the one writer takes it from
    the row it was handed and there is nothing for a caller to get wrong.

    Must be called inside @transaction.atomic.
    """
    if charge.compensates_id is not None:
        raise ValueError(
            "a correction corrects the original charge, not another "
            "correction: name the charge this trail starts from")
    ordinal = charge.compensations.count() + 1
    return Charge.objects.create(
        tenant_id=charge.tenant_id,
        task_id=charge.task_id,
        amount_micros=-charge.amount_micros,
        currency=charge.currency,
        agreed_price_line_id=charge.agreed_price_line_id,
        book_version=charge.book_version,
        resolved_at=charge.resolved_at,
        # DATED NOW, BECAUSE A CORRECTION IS ITS OWN MOVEMENT OF MONEY. Copying
        # the original's instant would date the correction into a period that
        # may already have been pushed, which is the failure `charged_at` is
        # dated at delivery to avoid, arriving from the other direction.
        charged_at=timezone.now(),
        idempotency_key=derived_key(charge.task_id, correction=ordinal),
        compensates=charge,
        correction_note=note,
        **_the_grouping_values_on(charge))


def the_work_was_charged(task):
    """Whether an original charge exists for ``task``.

    What the close renders as `charge_created` on a REPLAY. A replay returns
    what the first call returned — the start gate hands back the original piece
    of work rather than a second one — and this field is not an exception: a
    retrying caller asking *did my close bill this?* answered `false` for work
    that HAD been charged would be told something false about money.
    """
    return Charge.objects.filter(task=task, compensates__isnull=True).exists()


def _the_grouping_values_on(record):
    """The ten slots, by name, off whichever record carries them.

    One reader for the work and for a charge alike, because both carry the same
    ten columns for the same reason — and a second copy of this loop is a second
    chance for one of them to stop at nine.
    """
    return {slot: getattr(record, slot) for slot in _GROUPING_SLOTS}


#: Read off the model being written rather than counted out, so a slot arriving
#: on the record reaches the snapshot without an edit here. Ten today, matching
#: the registry — and the same ten a unit of work carries, which is what lets one
#: reader serve both sources.
_GROUPING_SLOTS = tuple(
    field.name for field in Charge._meta.get_fields()
    if field.name.startswith("grouping_field_"))

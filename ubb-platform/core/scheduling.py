"""The safety rails on a caller-supplied effective instant (#359, spec §8).

**A CHANGE CAN BE DATED FORWARD, AND NOTHING RUNS AT THE INSTANT IT NAMES.** The
rows are written when the act lands, carrying the boundary as a value the
resolver reads — no task, no periodic job, no signal. A late job would price
every event in the gap at the old rate, and that wrong price would sit
permanently on an authoritative record in a system with no re-invoice path
behind it. So the only thing that stands between a tenant and a schedule is
whether the instant they named is one this platform will honour, which is what
this module answers.

**⚠ THE HORIZON IS A PLATFORM CONSTANT AND IT IS NOT A TENANT SETTING.** Three
arguments, and they are the answer to anyone who wants it configurable:

* The bound exists to stop **a typo becoming a permanent invisible schedule**,
  which is the only failure mode anyone has described. A year is comfortably
  beyond any real pricing decision.
* **A configurable bound invites a tenant to set it to a century**, which
  defeats it. Map #137's *"tenant defines everything"* is about **catalogue** —
  what a tenant meters and charges — not about safety rails on a scheduling
  surface. A rail a tenant can move is a rail nobody is holding.
* **366 rather than 365**, so that a contract dated *"the same day next year"*
  across a leap year is not refused for being one day too far.

**⚠ IT IS DELIBERATELY NOT `REPORT_WINDOW_MAX_DAYS`, WHICH IS ALSO 366.** That
one bounds how wide a report window a caller may ask the database to scan; this
one bounds how far ahead a decision may be dated. Two different questions that
happen to have the same answer today, and sharing a symbol would let a change to
either silently move the other — the shape ADR-0006 §3 names, one value standing
in for two facts.

**WHY THERE IS A FLOOR TOO, AND WHY IT IS NAMED.** Dating a change *forward* is
what the instant is for, and a caller who means "now" omits it — so a boundary
behind the present is a **retroactive reprice**, which is the very thing
`Rate.valid_from` is declared FROZEN to prevent: *"moving it retroactively
re-costs work that has already reported"*. It carries `effective_at_in_past`, the
mirror of the recording route's `effective_at_in_future`, and it is named for the
same reason the ceiling is. On the declaring route `validation_error` already
means *"you have not declared that grouping field"* and *"that rule is not there
to reprice"*; a third meaning would leave a tenant's automation unable to tell a
date it can fix from a body it cannot, which is exactly the distinguishability
ruling 14a bought for the ceiling. **Found by both `/code-review` axes
independently, which is why the first draft's unnamed `validation_error` is not
what shipped.**

⚠ **THE FLOOR NARROWS THE DELIBERATE PATH AND DOES NOT CLOSE THE ACCIDENTAL
ONE**, and saying so is the honest version of a claim the first draft
overreached on. It refuses an instant a caller *states* in the past. It cannot
refuse the other way in: a draft declared with no instant takes the moment it
was declared, and publishing it later writes that now-past moment as the
boundary. The same check at publish time cannot tell that from the ordinary case,
because the ordinary case IS a declaration seconds stale. So `card_cache`'s
standing sentence — that entries for instants before a new boundary stay correct
forever — is **conditional on nobody publishing a stale draft, and it was
already conditional before this rail existed**. This module narrows it; it does
not make it true, and #358's split is where the remaining path comes from.

⚠ **The stronger floor is a later ticket's and it is not this one.** #360 replaces
"at or after now" with *"at or after the latest already-scheduled boundary in
that book"*, which is a rule about a book rather than about a clock and is
vacuous where a book has nothing scheduled. The two compose; neither subsumes
the other.

**THE SKEW ALLOWANCE IS THE RECORDING ROUTE'S, FOR THE RECORDING ROUTE'S
REASON, AND IT IS ON THE FLOOR ALONE.** A caller that stamps its own clock's
"now" and is refused by two hundred milliseconds has been told its clock is
wrong, which is not the refusal anybody wanted. Five minutes is what
`usage_service` already tolerates in the other direction, and it bounds
backdating to a window in which a reprice and a scheduling race are
indistinguishable anyway. **The ceiling gets none**: a year out, five minutes
of slack decides nothing, and the bound reads better as the exact number the
argument for it names.
"""
from datetime import timedelta

from core.problems import Problem

#: HOW FAR AHEAD A DECISION MAY BE DATED. See the module docstring for the three
#: arguments and for why this is not `REPORT_WINDOW_MAX_DAYS`.
MAX_FORWARD_SCHEDULING_DAYS = 366

#: Tolerated clock skew BELOW the present, and nowhere else — the ceiling is a
#: year out and decides nothing five minutes either way. The same allowance
#: `usage_service` makes on a recorded event's own moment, in the other
#: direction.
CLOCK_SKEW = timedelta(minutes=5)


def validate_scheduled_instant(effective_at, now):
    """Refuse an effective instant this platform will not honour.

    Raises `Problem` — the one coded refusal the composition layer renders as
    problem+json — with:

    * ``effective_at_naive`` where the instant carries no timezone. A naive
      datetime is not a moment; comparing one to an aware moment raises rather
      than answering, so this is refused before either bound is read and not as
      a consequence of one.
    * ``effective_at_too_far_ahead`` beyond the horizon, which is the named
      error ruling 14a asks for: a tenant's automation has to be able to tell
      *"that date is a typo"* apart from every other reason a body is refused.
    * ``effective_at_in_past`` below the present, allowing the skew above, for
      the reason the module docstring gives — and named rather than folded into
      ``validation_error`` for the same reason the ceiling is.

    ⚠ **IT READS NOTHING BUT ITS TWO ARGUMENTS.** No tenant, no book, no
    settings module, no database. That is what makes the horizon a platform
    constant rather than a default — there is no row a tenant could write that
    would reach this function — and it is also what lets a route put the call
    above everything it does, so a refused request spends nothing.
    """
    if effective_at.tzinfo is None or effective_at.utcoffset() is None:
        raise Problem(
            "effective_at_naive",
            "effective_at must be timezone-aware (e.g. 2027-01-01T00:00:00Z)")
    if effective_at > now + timedelta(days=MAX_FORWARD_SCHEDULING_DAYS):
        raise Problem(
            "effective_at_too_far_ahead",
            f"effective_at is more than {MAX_FORWARD_SCHEDULING_DAYS} days "
            f"ahead. The horizon is a platform bound and no tenant setting "
            f"moves it; it exists so that a mistyped year cannot become a "
            f"schedule nobody sees again")
    if effective_at < now - CLOCK_SKEW:
        raise Problem(
            "effective_at_in_past",
            "effective_at is in the past. A change is dated forward or not at "
            "all — omit effective_at to mean now — because a boundary behind "
            "the present reprices work that has already been recorded")

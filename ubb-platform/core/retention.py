"""The two clocks this platform keeps, and what each one still holds (#153 §12).

**ONE PLATFORM-WIDE ECONOMIC HORIZON AND ONE PLATFORM-WIDE MEASUREMENT HORIZON.
BOTH PUBLISHED.** No per-tenant policies, no per-record clocks, no archival
tiers, no per-chart horizons — spec §13, and the list is exhaustive on purpose:
every one of those would make *how far back can I ask?* a question with a
different answer per caller, and the answer has to be on the response.

**WHY TWO AND NOT ONE.** A closed period's figures restate whenever its facts
resolve, at any age, which is only true while the rows are still there — so the
money is kept for six years. Measurement detail is bulky, high-volume and
carries no dispute value, which is the argument for pruning it far sooner. The
two pressures reconcile only if the money and the bulk are on different clocks.

**WHAT EACH ONE COVERS.**

    economic       charges · economic postings · supplied revenue records ·
                   immutable receipts · statuses · applied monetary values ·
                   currency · attribution · rate provenance
    measurement    raw measurement records · quantities · component
                   drill-down · the measurement-concept rollup · fine-grained
                   quantity series

⚠ **THE MEASUREMENT HORIZON IS 400 DAYS BY DEFAULT, AND IT IS A SETTING** (#190
comment 5785029955; W5 ruling 7). About thirteen months of fine measurement
detail, deliberately conservative for launch — and NOT a claim that arbitrary
year-over-year detailed comparisons are supported: comparing a trailing year
with the year before it needs closer to two years of detail. `config.settings`
gives the default and the environment may override it; a change is a
configuration change and not a contract change. The daily prune
(`apps/metering/usage/pruning.py`) enforces it, releasing and deleting the
measurement records older than the CURRENT horizon whose postings are resolved.

⚠ **AND WHAT THE PUBLISHED HORIZON PROMISES** (ruling 11): detail from the
horizon onwards is guaranteed to be there. It is not a claim that nothing older
is physically present — a run cap can leave a backlog the prune catches up over
the following days — so read it as the guaranteed edge, not the literal oldest
row.

⚠ **AND THE ECONOMIC HORIZON IS THE OPPOSITE — A PLATFORM CONSTANT, DELIBERATELY
NOT CONFIGURABLE.** `core.scheduling`'s forward horizon carries the argument in
full and it holds here: six years is a published promise about what UBB will
still answer for, and a promise a tenant setting could shorten is not one. The
two knobs in this file are asymmetric on purpose and each says why.

⚠ **WHAT THE HORIZONS ARE NOT: THE PER-CALL WINDOW BOUND.** `core.time_windows`
holds how far ONE request may span — 366 days, 92 for an hourly question — and
this holds how far back the platform still has anything to answer with. Two
different subjects, and a contract stating one without the other publishes two
numbers that do not compose: *six years available* beside *at most one year per
request* leaves a caller to work out that six years takes six requests. They are
therefore stated TOGETHER on the surface that publishes them, which is the
honest minimum and is not the same as raising the bound. Raising it, or adding
an export path, is a capacity decision and #194's.
"""
from datetime import date, timedelta
from typing import NamedTuple

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

#: THE ECONOMIC HORIZON, IN CALENDAR YEARS. Six, matching the receipt floor
#: already published (#148 §10.1, §16) rather than a second number beside it.
#:
#: Years rather than days because that is what the promise says, and a day count
#: standing in for it would be the same fact in a spelling nobody can check
#: against the sentence a tenant read.
ECONOMIC_RETENTION_YEARS = 6

#: The setting that sets the shorter clock. A name rather than a direct
#: attribute read, so the one place that reads it and the tests that move it
#: agree by construction.
MEASUREMENT_RETENTION_DAYS_SETTING = "UBB_MEASUREMENT_RETENTION_DAYS"

#: The two names the horizons ship under, #153 §12.3's own (spec §4 keeps them).
#: ADR-0007 §3 makes a name final the moment it reaches `openapi/v1.json`, so
#: they are constants here and the schema's attribute names are held to them.
ECONOMIC_HORIZON_FIELD = "economic_data_available_from"
MEASUREMENT_HORIZON_FIELD = "measurement_data_available_from"

#: And the third name from the same sketch: the day one MEASURE's series can
#: start, carried on the measure that could not be stated. It repeats the
#: horizon the row was judged against rather than making a reader work out which
#: of the two above applied to it — which they could not, since which clock
#: governs a row depends on how the question was grouped.
AVAILABLE_FROM_FIELD = "available_from"


class RetentionHorizons(NamedTuple):
    """The earliest day each clock can still answer for, as of some day.

    Two dates that travel together everywhere, because a surface publishing one
    without the other tells a caller which series can start and leaves them to
    guess about the other.

    ⚠ **`measurement` IS NEVER EARLIER THAN `economic`** — see
    :func:`retention_horizons`, which makes that true by construction rather
    than by whoever types the number.
    """
    economic: date
    measurement: date


def retention_horizons(as_of: date) -> RetentionHorizons:
    """The earliest day each clock can still answer for.

    ⚠ **IT READS THE DAY IT IS GIVEN AND ONE SETTING, AND NOTHING ELSE.** No
    tenant, no row, no request — which is what makes these platform horizons
    rather than per-tenant policies, and what lets a read contract publish them
    without a query.
    """
    economic = _years_before(as_of, ECONOMIC_RETENTION_YEARS)
    days = getattr(settings, MEASUREMENT_RETENTION_DAYS_SETTING, None)
    if days is None:
        # ⚠ NEVER A SILENT SIX YEARS (W5 ruling 7). Until W5 a missing number
        # answered the economic horizon, which was true while nothing pruned a
        # measurement; a daily prune now enforces this clock, so a settings
        # module that does not state it is misconfigured, and saying so is
        # safer than publishing six years of detail the prune does not keep.
        raise ImproperlyConfigured(
            f"{MEASUREMENT_RETENTION_DAYS_SETTING} must be set: the measurement "
            f"horizon is published on every economic answer and the daily prune "
            f"enforces it")
    # ⚠ BOUNDED AT BOTH ENDS, AND EACH END IS A REAL MISCONFIGURATION RATHER
    # THAN DEFENSIVE DECORATION.
    #
    # Below: the shorter clock cannot claim history the longer one has already
    # released, whatever number is typed — a measurement record is a child of
    # its posting and cascades with it, so a clock set to a century would
    # publish an availability date for rows the economic clock has let go.
    #
    # Above: a number below zero has no reading. `0` already means *release
    # everything older than today*, so a negative one would only ever publish a
    # horizon in the FUTURE — a date no series can start from. It rounds to
    # zero, which claims the LEAST history, which is the direction this module
    # rounds in everywhere (see the leap day below): a platform that promises
    # less than it kept is recoverable and one that promises more is not.
    shorter = as_of - timedelta(days=max(days, 0))
    return RetentionHorizons(economic=economic,
                             measurement=max(economic, shorter))


def _years_before(day: date, years: int) -> date:
    """`day` less whole calendar years, and the one day that has no answer.

    ⚠ **A LEAP DAY FALLS FORWARD, NOT BACK.** Six years before 29 February is a
    date no calendar has. A horizon is a promise about what is still HELD, so
    the day to land on is the one claiming LESS history — 1 March of the target
    year rather than 28 February. One day either way decides nothing; which
    direction a boundary rounds decides whether an edge case makes the platform
    promise more than it kept.
    """
    try:
        return day.replace(year=day.year - years)
    except ValueError:
        return date(day.year - years, 3, 1)

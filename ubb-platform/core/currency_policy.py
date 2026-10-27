"""UBB v1 is US dollars only: the one currency policy for economic admission.

ADR-0023 is the rule; this module is where code asks it. It is two rules, not
one (the owner's ruling of 2026-10-26 on #555 and #564), and this module is
the first of them:

1. **Explicit non-USD money or configuration supplied through UBB's own
   economic doors is refused.** :func:`admit_currency` is that refusal, and it
   is the only one. The tenant door, both recording routes, a Cost Book, a
   reported cost's pinned currency and supplied revenue all ask it. Every column
   UBB's economics admit carries the database ``CHECK`` that
   :func:`usd_only_check` builds, so a write that goes round the doors — the
   admin form, ``QuerySet.update()``, ``psql`` — meets the same rule.
2. **A foreign-currency fact from an external integration is preserved as the
   source stated it and quarantined** before it can enter USD economics
   (#564). That is not a second policy. The quarantine asks
   :func:`is_admitted`, this module's own question, and keeps whatever fails it
   beside the economics, never inside them. A column that records what an
   external integration SENT is declared on its model under
   :data:`SOURCE_CURRENCY_COLUMNS`, and is the one kind of currency column no
   ``CHECK`` covers: a constraint there would make the database refuse the very
   evidence the quarantine exists to keep.

Nothing is converted and nothing is relabelled. There is no FX anywhere in UBB,
so there is no correct conversion to perform.

**Representation is not policy.** ``core.money``'s minor-unit table gives the
minor unit of each of eighteen currencies. That is what UBB can
*represent*, and it stays as wide as it is. What UBB *admits* into its
economics is this module's one value. Admitting a second currency is a decision
about FX, which v1 deliberately does not have — never an edit to that table.
"""

from django.db import models

from core.exceptions import StripeFatalError

#: THE CURRENCY UBB v1's ECONOMICS ARE DENOMINATED IN. Lowercase, the casing
#: every currency column in the tree uses and the payment rail's own.
ECONOMIC_CURRENCY = "usd"

#: The problem code a refusal answers with: the error catalogue's existing
#: entry, which the tenant door and supplied revenue already used.
UNSUPPORTED_CURRENCY = "unsupported_currency"

#: WHAT EVERY REVENUE AND MARGIN READ CALLS ITS COUNT OF EXCLUDED FOREIGN
#: SUBSCRIPTIONS (#564, the owner's ruling 5). One spelling, because the value
#: crosses products — subscriptions counts, the composition layer and the
#: alerting record publish — as `core.cost_totals`'s two counts do. Exact and
#: never null: UBB always knows how many subscriptions it left out, and 0
#: means none.
FOREIGN_CURRENCY_SUBSCRIPTION_COUNT_KEY = "foreign_currency_subscription_count"

#: What that count means, on every schema that publishes it.
FOREIGN_CURRENCY_SUBSCRIPTION_COUNT_MEANING = (
    "How many Stripe subscriptions the subscription revenue in this answer "
    "leaves out because Stripe holds them in a currency UBB does not admit. "
    "UBB v1 is US dollars only and converts nothing, so each is kept as "
    "Stripe stated it and excluded from every revenue and margin figure "
    "here; where this is non-zero the true revenue, and so the margin, is "
    "higher by an amount UBB cannot state in dollars. Exact, scoped like the "
    "figures it qualifies, and 0 where nothing was left out.")

#: The model attribute naming a currency column that records what an external
#: integration sent. Each such column is spared the ``CHECK`` (module docstring,
#: rule 2), and ``apps/platform/tests/test_v1_is_usd_only.py`` holds every
#: other currency column to it.
SOURCE_CURRENCY_COLUMNS = "SOURCE_CURRENCY_COLUMNS"


class UnsupportedCurrency(ValueError):
    """A non-USD currency offered at one of UBB's own economic doors."""

    code = UNSUPPORTED_CURRENCY


def is_admitted(currency) -> bool:
    """Whether ``currency`` names UBB's economic currency, read the way a door
    reads it: case and surrounding space are spelling, never a second currency.
    """
    return (isinstance(currency, str)
            and currency.strip().lower() == ECONOMIC_CURRENCY)


def admit_currency(currency) -> str:
    """The one refusal: ``currency`` in its stored spelling, or
    :class:`UnsupportedCurrency`."""
    if not is_admitted(currency):
        raise UnsupportedCurrency(
            f"unsupported currency {currency!r}: UBB v1 admits US dollars "
            f"only ({ECONOMIC_CURRENCY!r}) and converts nothing — there is "
            f"no FX, so no other currency can enter its economics")
    return ECONOMIC_CURRENCY


class CurrencyDisagreement(StripeFatalError):
    """An outbound money call refused before anything was sent (#565).

    A ``StripeFatalError`` because that is what it is to every caller of the
    rail: not retryable, and not a transient failure. Retrying a call whose
    records disagree about the currency would send the same disagreement
    again.
    """


def the_rails_currency(record, currency, agreeing=None):
    """The currency an outbound money call sends: read off ``record``, the
    authoritative monetary object it draws on (ADR-0023 §7, #565).

    ``agreeing`` maps every other record the same amount is drawn against or
    credited to, by what it is, to its currency. The call is refused — never
    reconciled — when the record's currency is not one UBB admits, or when
    any of those disagrees with it. The database already holds every
    economic column to US dollars, so this never fires on a record UBB wrote;
    it is the rail PROVING the invariant rather than assuming it, which is
    why each adapter asks it on its own and why a rule lifted below it is
    still refused here.
    """
    if not is_admitted(currency):
        raise CurrencyDisagreement(
            f"{record} is in {currency!r}, which UBB v1 does not admit "
            f"({ECONOMIC_CURRENCY!r} only); nothing was sent")
    sending = admit_currency(currency)
    for other, theirs in (agreeing or {}).items():
        if not is_admitted(theirs) or admit_currency(theirs) != sending:
            raise CurrencyDisagreement(
                f"{record} is in {sending!r} and {other} is in {theirs!r}: "
                f"UBB never sends an amount in one currency against a "
                f"record in another, and reconciles nothing; nothing was "
                f"sent")
    return sending


def usd_only_check(field, name, *, or_blank=False):
    """The database's half of the rule, for one column.

    ``or_blank`` admits the empty string beside it, for a column whose blank
    means "declared elsewhere" rather than a currency (the reported cost's
    pinned code, blank exactly when a path into the supplier's response
    names the currency instead).
    """
    condition = models.Q(**{field: ECONOMIC_CURRENCY})
    if or_blank:
        condition |= models.Q(**{field: ""})
    return models.CheckConstraint(condition=condition, name=name)


def refuse_rows_outside_the_policy(table, column, *, or_blank=False):
    """A migration step that runs before a column's ``CHECK`` is installed.

    It reconciles nothing, because there is nothing honest to reconcile *to*.
    A row in another currency cannot be converted (no FX) and must not be
    relabelled, so the migration stops and says which rows to deal with. A
    stored ``'USD'`` is refused the same way: the column's spelling is
    lowercase, and a migration that rewrote it would be deciding a row's
    meaning on a reader's behalf.
    """
    admitted = [ECONOMIC_CURRENCY, *([""] if or_blank else [])]

    def refuse(apps, schema_editor):
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {column}, count(*) FROM {table} "
                f"WHERE NOT ({column} = ANY(%s)) GROUP BY {column} "
                f"ORDER BY {column}", [admitted])
            found = cursor.fetchall()
        if found:
            listed = ", ".join(f"{value!r} x{count}" for value, count in found)
            raise RuntimeError(
                f"{table}.{column} holds rows outside UBB v1's one currency "
                f"({listed}). ADR-0023: UBB converts nothing and relabels "
                f"nothing, so this migration will not do either. Correct or "
                f"remove those rows, then migrate again.")

    return refuse

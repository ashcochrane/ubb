"""Shared setup for a Plan, which cannot exist without a Pricing Book (#362).

`docs/conventions/testing.md` puts shared setup here rather than in each
module, and this one has a second reason to be shared: it calls the two
production doors the plans route calls, in the order it calls them. A fixture
that hand-rolled the construction would be a second writer of it and would keep
passing the day one of those doors changed (#354).

⚠ **THIS IS THE FIRST MODULE UNDER `apps/platform/**` TO NAME A PRODUCT, AND
THAT IS SAID HERE BECAUSE NO GATE WILL SAY IT.** ADR-001's walker excludes
`tests/` directories outright, so the import below is invisible to the rule
that "the kernel imports no product" — and a reader who found it later would
have to work out whether it was a breach or a carve-out. It is a carve-out, on
one narrow ground: a Plan cannot be created without a book, only metering can
make a book, and this is a FIXTURE rather than a code path. The kernel's own
production modules import nothing from metering, which
`test_a_plan_names_the_book_it_prices_from.py` asserts directly rather than
leaving to the walker. If that ever stops being true of a `plans/` module that
is not this one, the walker catches it.
"""
from apps.metering.pricing.services.book_service import BookService
from apps.platform.plans.services import PlanService


def a_plan(*, tenant, key="std", name="", **fields):
    """A Plan and the empty Pricing Book it prices from.

    The book is created FIRST — that ordering is the ticket's subject and not
    an implementation detail of this helper — and it holds no rules, which is
    the state a plan is in until its tenant publishes some.
    """
    book = BookService.the_book_a_plan_prices_from(
        tenant, plan_key=key, plan_name=name or key)
    return PlanService.create(tenant, pricing_book_id=book.id,
                              key=key, name=name or key, **fields)

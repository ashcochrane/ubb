"""The webhook catalogue publishes exactly the registry's names, and none it
retired (#222, the terminal-event split, #464).

Twenty published names were renamed or split over three slices, and every
payload class takes its name from `core.vocabulary` now, so the catalogue
cannot publish a name the registry does not declare. What is held here is the
end state those renames left, in both directions:

* every name the registry declares is published, and nothing else is — a
  declared name nothing publishes would be a contract promise about an event
  that never fires;
* no name the registry RETIRED is published again — a retired name back in the
  catalogue would be a subscription target the console, the SDK and every
  generated client were told is gone.

Before the cutover (#190) the second half was asserted three times, once
against each rename migration's own map (`events/0007`, `0008` and `0009`),
as that migration's premise. The maps left with the migrations; the registry's
`retired_aliases` is the one list of what was retired, and it is read here. The
registry-side twin, which also holds the aliases apart from the live values,
is `tests/contracts/test_webhook_catalogue.py`.
"""
from apps.platform.events.catalog import WEBHOOK_EVENT_TYPES
from apps.platform.events.schemas import payload_schema_classes
from apps.platform.events.tests._helpers import retired_event_names
from core.vocabulary import WEBHOOK_EVENT_TYPE_VALUES


def test_the_catalogue_publishes_exactly_the_registrys_set():
    """The assertion the fifth rename made true, in place of the tripwire that
    waited for it (#222's `DEFERRED` and its test, deleted in #464).

    Every payload class takes its name from `core.vocabulary`, so the
    catalogue cannot publish a name the registry does not declare — and this
    holds the other direction too: a declared name nothing publishes would be
    a contract promise about an event that never fires.
    """
    assert set(WEBHOOK_EVENT_TYPES) == set(WEBHOOK_EVENT_TYPE_VALUES)
    assert len(WEBHOOK_EVENT_TYPES) == len(payload_schema_classes())


def test_no_name_the_registry_retired_is_published():
    """Read off the registry, never spelled. The count is the control: a walk
    that read nothing would make the disjointness below hold vacuously, and
    §5.4's twenty retirements are what the registry records."""
    retired = retired_event_names()

    assert len(retired) == len(set(retired)) == 20, retired
    still_published = sorted(set(retired) & set(WEBHOOK_EVENT_TYPES))
    assert not still_published, (
        f"{still_published} are retired and published again")

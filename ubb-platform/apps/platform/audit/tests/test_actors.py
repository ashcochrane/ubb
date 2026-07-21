"""Audit actors: the four kinds live from day one, their display snapshots, and
the request-scoped capture/reset contextvar (ADR-004 §4)."""
import contextvars

from django.test import SimpleTestCase

from apps.platform.audit import actors
from apps.platform.audit.actors import (
    API_KEY,
    END_CUSTOMER,
    MEMBER,
    OPERATOR,
    OPERATOR_DISPLAY,
    SYSTEM,
    Actor,
    api_key_actor,
    clear_current_actor,
    end_customer_actor,
    get_current_actor,
    member_actor,
    operator_actor,
    set_current_actor,
)


class ActorKindsTest(SimpleTestCase):
    def test_four_kinds_live_plus_system_reserved(self):
        # ADR-004 §4: four actor kinds from day one, `system` reserved/deferred.
        self.assertEqual(
            {MEMBER, API_KEY, OPERATOR, END_CUSTOMER},
            {"member", "api_key", "operator", "end_customer"})
        self.assertEqual(SYSTEM, "system")


class ActorBuildersTest(SimpleTestCase):
    def test_member_actor_display_is_email(self):
        a = member_actor("m-1", "sam@example.com")
        self.assertEqual((a.kind, a.id, a.display),
                         (MEMBER, "m-1", "sam@example.com"))

    def test_api_key_actor_display_is_label(self):
        a = api_key_actor("k-1", "CI key")
        self.assertEqual((a.kind, a.id, a.display), (API_KEY, "k-1", "CI key"))

    def test_api_key_actor_unlabelled_falls_back_to_generic_name(self):
        a = api_key_actor("k-2", "")
        self.assertEqual(a.display, "API key")

    def test_operator_actor_always_renders_ubb_operator(self):
        # The feed records THAT staff acted, never WHICH staffer (ADR-004 §4).
        self.assertEqual(operator_actor().display, "UBB operator")
        self.assertEqual(operator_actor("staff-42").display, OPERATOR_DISPLAY)
        self.assertEqual(operator_actor("staff-42").id, "staff-42")
        self.assertEqual(operator_actor().kind, OPERATOR)

    def test_end_customer_actor_display_is_external_id(self):
        a = end_customer_actor("c-1", "cust_abc")
        self.assertEqual((a.kind, a.id, a.display),
                         (END_CUSTOMER, "c-1", "cust_abc"))

    def test_actor_is_immutable(self):
        a = Actor(kind=MEMBER, id="x", display="y")
        with self.assertRaises(Exception):
            a.kind = OPERATOR  # frozen dataclass


class ActorContextvarTest(SimpleTestCase):
    def tearDown(self):
        clear_current_actor()

    def test_set_get_clear_roundtrip(self):
        self.assertIsNone(get_current_actor())
        a = member_actor("m-1", "sam@example.com")
        set_current_actor(a)
        self.assertEqual(get_current_actor(), a)
        clear_current_actor()
        self.assertIsNone(get_current_actor())

    def test_capture_is_isolated_per_context(self):
        # A fresh contextvars.Context does not see another context's actor —
        # the property that makes per-request/per-thread isolation possible.
        set_current_actor(member_actor("outer", "outer@x.com"))

        seen = {}

        def _inner():
            seen["before"] = get_current_actor()
            set_current_actor(api_key_actor("inner", "inner"))
            seen["after"] = get_current_actor()

        contextvars.copy_context().run(_inner)
        # The child context started from the current value...
        self.assertEqual(seen["before"].id, "outer")
        # ...but its own set() never leaked back out to us.
        self.assertEqual(get_current_actor().id, "outer")
        self.assertEqual(seen["after"].id, "inner")

"""RequestActorMiddleware resets the request-scoped actor at request end, so a
pooled worker thread never leaks one request's principal into the next."""
from django.test import SimpleTestCase

from apps.platform.audit.actors import (
    clear_current_actor,
    get_current_actor,
    member_actor,
    set_current_actor,
)
from core.middleware import RequestActorMiddleware


class RequestActorMiddlewareTest(SimpleTestCase):
    def tearDown(self):
        clear_current_actor()

    def test_actor_is_cleared_after_the_request(self):
        captured = {}

        def get_response(request):
            # Simulate the auth seam capturing an actor mid-request.
            set_current_actor(member_actor("m-1", "sam@example.com"))
            captured["during"] = get_current_actor()
            return "response"

        mw = RequestActorMiddleware(get_response)
        result = mw(object())

        self.assertEqual(result, "response")
        self.assertIsNotNone(captured["during"])  # was set during the request
        self.assertIsNone(get_current_actor())     # cleared afterwards

    def test_actor_is_cleared_even_when_the_view_raises(self):
        def get_response(request):
            set_current_actor(member_actor("m-1", "sam@example.com"))
            raise RuntimeError("boom")

        mw = RequestActorMiddleware(get_response)
        with self.assertRaises(RuntimeError):
            mw(object())
        self.assertIsNone(get_current_actor())

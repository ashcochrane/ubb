"""The `Operation` value: what a hand-written method names instead of a path.

#209, from #155 §8.3. Every request the ergonomic surface makes now spells its
target as a registry constant, and this is the type those constants are. The
rules it enforces at runtime are the ones the gate enforces statically, so a
mistake is caught twice and never later than the first call.

The behaviour that matters is narrow and load-bearing: unpacking an operation
must produce exactly the ``(method, path)`` pair `_request` already took, or the
81 call sites would have changed shape and the SDK suite would have had to be
rewritten to match — which is the one thing #209 may not do.
"""

import unittest

from ubb._operation import Operation


class UnparameterisedTest(unittest.TestCase):
    """A route with no parameters unpacks straight into a request."""

    def setUp(self):
        self.operation = Operation(
            "api_v1_tenant_endpoints_get_tenant_config", "get",
            "/api/v1/tenant/config")

    def test_unpacks_to_the_method_and_path_request_already_took(self):
        self.assertEqual(tuple(self.operation), ("get", "/api/v1/tenant/config"))

    def test_star_unpacking_is_the_call_shape(self):
        """The shape every converted call site uses, asserted as such."""
        def _request(method, path, **kwargs):
            return method, path, kwargs

        self.assertEqual(
            _request(*self.operation, json={"a": 1}),
            ("get", "/api/v1/tenant/config", {"json": {"a": 1}}))

    def test_calling_it_with_no_arguments_is_the_same_pair(self):
        """Uniformity for a caller that would rather always call."""
        self.assertEqual(self.operation(), ("get", "/api/v1/tenant/config"))

    def test_it_carries_no_parameters(self):
        self.assertEqual(self.operation.parameters, ())

    def test_a_stray_argument_is_refused(self):
        with self.assertRaises(TypeError) as raised:
            self.operation("extra")
        self.assertIn("takes no parameters", str(raised.exception))
        self.assertIn("api_v1_tenant_endpoints_get_tenant_config",
                      str(raised.exception))


class ParameterisedTest(unittest.TestCase):
    """A route with parameters is filled positionally, in path order."""

    def setUp(self):
        self.operation = Operation(
            "api_v1_billing_endpoints_void_grant", "post",
            "/api/v1/billing/customers/{customer_id}/grants/{grant_id}/void")

    def test_it_names_its_parameters_in_path_order(self):
        self.assertEqual(self.operation.parameters, ("customer_id", "grant_id"))

    def test_calling_it_fills_them_in_order(self):
        self.assertEqual(
            self.operation("cus_1", "grant_2"),
            ("post",
             "/api/v1/billing/customers/cus_1/grants/grant_2/void"))

    def test_the_filled_path_is_what_the_f_string_produced(self):
        """The refactor's whole safety claim, stated as an assertion.

        Every converted call site used to build this string with an f-string.
        If filling differs from interpolation by so much as a slash, 81 methods
        change what they call and the SDK suite is the only thing that would
        say so.
        """
        customer_id, grant_id = "cus_1", "grant_2"
        self.assertEqual(
            self.operation(customer_id, grant_id)[1],
            f"/api/v1/billing/customers/{customer_id}/grants/{grant_id}/void")

    def test_values_are_stringified_rather_than_quoted(self):
        """As the f-strings did. Adding percent-encoding here would silently
        change what 39 interpolated call sites send."""
        operation = Operation("things_read", "get", "/api/v1/things/{thing_id}")
        self.assertEqual(operation(7)[1], "/api/v1/things/7")

    def test_too_few_arguments_are_refused_by_name(self):
        with self.assertRaises(TypeError) as raised:
            self.operation("cus_1")
        message = str(raised.exception)
        self.assertIn("2", message)
        self.assertIn("customer_id", message)
        self.assertIn("grant_id", message)

    def test_too_many_arguments_are_refused(self):
        with self.assertRaises(TypeError):
            self.operation("cus_1", "grant_2", "spare")

    def test_unpacking_one_that_needs_parameters_is_refused(self):
        """`*OP` on a parameterised route would send `{customer_id}` verbatim.

        Silently, and to a real server, which is the exact class of mistake
        #209 exists to make unwriteable. The gate refuses it statically; this
        refuses it at runtime for anyone reaching the type another way.
        """
        with self.assertRaises(TypeError) as raised:
            tuple(self.operation)
        self.assertIn("customer_id", str(raised.exception))


class AnonymousParameterTest(unittest.TestCase):
    """A route whose parameter names are not recorded — positions, no names.

    The migration ledger stores an excused path with each parameter collapsed
    to ``{}``, which is the identity the gate matches on, so a constant
    generated from an entry has anonymous positions where a published one has
    named parameters. This is a property of the TYPE and holds whether or not
    any entry exists.

    ⚠ It said "the three dead calls are generated from those entries" until
    #373, and its fixture was one of those three routes. All three are deleted,
    the ledger's G17 family is empty, and no `UNPUBLISHED_` constant is
    rendered today — so the sentence was a present-tense claim about something
    that had gone, in a file the deletion never touched. The route below is
    deliberately synthetic now: a fixture that is nobody's real path cannot go
    stale the same way twice, and the type does not care which path it is.
    """

    def setUp(self):
        self.operation = Operation(None, "put", "/api/v1/nothing/publishes/{}")

    def test_an_anonymous_position_is_still_a_parameter(self):
        self.assertEqual(len(self.operation.parameters), 1)

    def test_it_fills_the_same_way(self):
        self.assertEqual(
            self.operation("pub_9"),
            ("put", "/api/v1/nothing/publishes/pub_9"))

    def test_arity_is_still_checked(self):
        with self.assertRaises(TypeError):
            self.operation()


class ReadabilityTest(unittest.TestCase):
    def test_it_reads_as_the_request_it_makes(self):
        """A repr a traceback can be read through."""
        operation = Operation("things_read", "get", "/api/v1/things/{thing_id}")
        self.assertEqual(repr(operation), "<Operation GET /api/v1/things/{thing_id}>")


if __name__ == "__main__":
    unittest.main()

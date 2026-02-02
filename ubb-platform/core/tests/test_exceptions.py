from django.test import TestCase
from core.exceptions import (
    UBBError,
    StripeTransientError,
    StripePaymentError,
    StripeFatalError,
)


class StripeExceptionHierarchyTest(TestCase):
    def test_transient_error_is_ubb_error(self):
        err = StripeTransientError("rate limited")
        self.assertIsInstance(err, UBBError)

    def test_payment_error_is_ubb_error(self):
        err = StripePaymentError("card declined", code="card_declined", decline_code="insufficient_funds")
        self.assertIsInstance(err, UBBError)
        self.assertEqual(err.code, "card_declined")
        self.assertEqual(err.decline_code, "insufficient_funds")

    def test_fatal_error_is_ubb_error(self):
        err = StripeFatalError("invalid api key")
        self.assertIsInstance(err, UBBError)

    def test_transient_error_message(self):
        err = StripeTransientError("network timeout")
        self.assertEqual(str(err), "network timeout")

    def test_payment_error_defaults(self):
        err = StripePaymentError("declined")
        self.assertIsNone(err.code)
        self.assertIsNone(err.decline_code)

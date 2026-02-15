import stripe
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from core.exceptions import StripeTransientError, StripePaymentError, StripeFatalError
from apps.billing.stripe.services.stripe_service import stripe_call, validate_amount_micros, micros_to_cents, StripeService


class StripeCallWrapperTest(TestCase):
    def test_successful_call(self):
        mock_fn = MagicMock(return_value="result")
        result = stripe_call(mock_fn, arg1="val1")
        self.assertEqual(result, "result")
        mock_fn.assert_called_once_with(arg1="val1")

    def test_rate_limit_raises_transient(self):
        mock_fn = MagicMock(side_effect=stripe.error.RateLimitError("rate limited"))
        with self.assertRaises(StripeTransientError):
            stripe_call(mock_fn, retryable=False)

    def test_card_error_raises_payment_error(self):
        err = stripe.error.CardError("declined", "param", "card_declined")
        mock_fn = MagicMock(side_effect=err)
        with self.assertRaises(StripePaymentError):
            stripe_call(mock_fn)

    def test_auth_error_raises_fatal(self):
        mock_fn = MagicMock(side_effect=stripe.error.AuthenticationError("bad key"))
        with self.assertRaises(StripeFatalError):
            stripe_call(mock_fn)

    def test_idempotency_error_raises_fatal(self):
        mock_fn = MagicMock(side_effect=stripe.error.IdempotencyError("mismatch"))
        with self.assertRaises(StripeFatalError):
            stripe_call(mock_fn)

    @patch("apps.billing.stripe.services.stripe_service.time.sleep")
    def test_retryable_with_idempotency_key_retries(self, mock_sleep):
        mock_fn = MagicMock(
            side_effect=[
                stripe.error.APIConnectionError("timeout"),
                "success",
            ]
        )
        result = stripe_call(mock_fn, retryable=True, idempotency_key="key-1", max_retries=2)
        self.assertEqual(result, "success")
        self.assertEqual(mock_fn.call_count, 2)

    def test_retryable_without_key_does_not_retry(self):
        mock_fn = MagicMock(side_effect=stripe.error.APIConnectionError("timeout"))
        with self.assertRaises(StripeTransientError):
            stripe_call(mock_fn, retryable=True, idempotency_key=None)
        self.assertEqual(mock_fn.call_count, 1)

    def test_amount_validation_rejects_zero(self):
        with self.assertRaises(StripeFatalError):
            validate_amount_micros(0)

    def test_amount_validation_rejects_negative(self):
        with self.assertRaises(StripeFatalError):
            validate_amount_micros(-100)

    def test_amount_validation_accepts_positive(self):
        validate_amount_micros(1_000_000)  # should not raise

    def test_micros_to_cents_valid(self):
        self.assertEqual(micros_to_cents(1_500_000), 150)

    def test_micros_to_cents_fractional_raises(self):
        with self.assertRaises(StripeFatalError):
            micros_to_cents(1_500_001)

    def test_micros_to_cents_zero(self):
        self.assertEqual(micros_to_cents(0), 0)


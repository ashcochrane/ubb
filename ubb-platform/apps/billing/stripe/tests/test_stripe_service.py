import stripe
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from core.exceptions import StripeTransientError, StripePaymentError, StripeFatalError
from apps.billing.stripe.services.stripe_service import (
    StripeService, field, metadata_value, micros_to_cents, stripe_call,
    validate_amount_micros)


def _card_error(code="card_declined", decline_code="insufficient_funds",
                payment_intent="pi_declined"):
    """A CardError exactly as stripe-python 15.2.0 builds one from Stripe's
    response body: ``decline_code`` and ``payment_intent`` live on
    ``e.error`` (the ErrorObject), NOT as top-level attributes."""
    body = {"error": {"type": "card_error", "code": code, "message": "declined",
                      "param": "payment_method"}}
    if decline_code is not None:
        body["error"]["decline_code"] = decline_code
    if payment_intent is not None:
        body["error"]["payment_intent"] = {
            "id": payment_intent, "object": "payment_intent",
            "status": "requires_payment_method"}
    return stripe.error.CardError("declined", "payment_method", code, json_body=body)


class TheAccessorReadsTheRealObjectModel(TestCase):
    """Stage C1a (F-3a/F-3b): ``field`` / ``metadata_value`` are the one
    place UBB spells the pinned SDK's object shape. Proved on a genuine
    constructed StripeObject AND on the plain dict the helper tolerates for
    exactly this test — the two sides of the supported boundary."""

    def setUp(self):
        self.pi = stripe.PaymentIntent.construct_from({
            "id": "pi_1", "object": "payment_intent", "status": "succeeded",
            "metadata": {"topup_attempt_id": "att-1"},
            "latest_charge": "ch_1", "description": None}, "sk_test_sentinel")

    def test_a_real_stripe_object_is_not_a_dict_and_has_no_get(self):
        self.assertNotIsInstance(self.pi, dict)
        self.assertFalse(hasattr(self.pi, "get"))
        self.assertNotIsInstance(self.pi.metadata, dict)
        self.assertFalse(hasattr(self.pi.metadata, "get"))
        # And an EMPTY StripeObject is truthy, so `x or {}` never falls back.
        self.assertTrue(stripe.StripeObject.construct_from({}, "sk_test_sentinel"))

    def test_field_reads_present_absent_and_none_on_a_real_object(self):
        self.assertEqual(field(self.pi, "status"), "succeeded")
        self.assertEqual(field(self.pi, "missing", "dflt"), "dflt")
        self.assertIsNone(field(self.pi, "missing"))
        self.assertEqual(field(self.pi, "description", "dflt"), "dflt")  # present, None

    def test_metadata_value_reads_nested_metadata_on_a_real_object(self):
        self.assertEqual(metadata_value(self.pi, "topup_attempt_id"), "att-1")
        self.assertIsNone(metadata_value(self.pi, "other"))
        bare = stripe.PaymentIntent.construct_from(
            {"id": "pi_2", "object": "payment_intent"}, "sk_test_sentinel")
        self.assertIsNone(metadata_value(bare, "topup_attempt_id"))
        empty = stripe.PaymentIntent.construct_from(
            {"id": "pi_3", "object": "payment_intent", "metadata": {}}, "sk_test_sentinel")
        self.assertEqual(metadata_value(empty, "topup_attempt_id", ""), "")

    def test_a_string_where_an_object_was_hoped_for_has_no_fields(self):
        # An unexpanded `price.product` is an id string.
        self.assertIsNone(field("prod_123", "name"))
        self.assertIsNone(field(None, "name"))

    def test_the_plain_dict_side_of_the_boundary(self):
        d = {"metadata": {"topup_attempt_id": "att-9"}, "status": None}
        self.assertEqual(field(d, "metadata"), {"topup_attempt_id": "att-9"})
        self.assertEqual(field(d, "status", "dflt"), "dflt")
        self.assertEqual(metadata_value(d, "topup_attempt_id"), "att-9")
        self.assertIsNone(metadata_value({}, "topup_attempt_id"))

    def test_field_never_returns_a_dict_method_for_a_dict(self):
        # "items" is a dict method name; the dict branch must read the KEY.
        self.assertEqual(field({"items": {"data": []}}, "items"), {"data": []})
        self.assertIsNone(field({}, "items"))


class ThePaymentErrorCarriesTheRealCardErrorShape(TestCase):
    """O-1: the PaymentIntent id and decline code are read off ``e.error`` —
    where stripe-python puts them — so a declined or SCA-blocked attempt can
    record the intent it concerns."""

    def test_decline_code_and_payment_intent_id_are_read_from_e_error(self):
        err = _card_error()
        self.assertIsNone(getattr(err, "decline_code", None))  # not top-level
        mock_fn = MagicMock(side_effect=err)
        with self.assertRaises(StripePaymentError) as ctx:
            stripe_call(mock_fn, api_key="sk_test_x")
        self.assertEqual(ctx.exception.code, "card_declined")
        self.assertEqual(ctx.exception.decline_code, "insufficient_funds")
        self.assertEqual(ctx.exception.payment_intent_id, "pi_declined")

    def test_an_sca_challenge_carries_its_payment_intent_id(self):
        err = _card_error(code="authentication_required", decline_code=None,
                          payment_intent="pi_sca")
        with self.assertRaises(StripePaymentError) as ctx:
            stripe_call(MagicMock(side_effect=err), api_key="sk_test_x")
        self.assertEqual(ctx.exception.code, "authentication_required")
        self.assertIsNone(ctx.exception.decline_code)
        self.assertEqual(ctx.exception.payment_intent_id, "pi_sca")

    def test_an_unexpanded_payment_intent_id_string_is_kept(self):
        body = {"error": {"type": "card_error", "code": "card_declined",
                          "message": "declined", "payment_intent": "pi_plain"}}
        err = stripe.error.CardError("declined", "card", "card_declined", json_body=body)
        with self.assertRaises(StripePaymentError) as ctx:
            stripe_call(MagicMock(side_effect=err), api_key="sk_test_x")
        self.assertEqual(ctx.exception.payment_intent_id, "pi_plain")

    def test_a_card_error_without_a_body_still_maps(self):
        err = stripe.error.CardError("declined", "param", "card_declined")
        with self.assertRaises(StripePaymentError) as ctx:
            stripe_call(MagicMock(side_effect=err), api_key="sk_test_x")
        self.assertEqual(ctx.exception.code, "card_declined")
        self.assertIsNone(ctx.exception.decline_code)
        self.assertIsNone(ctx.exception.payment_intent_id)


class TheWrapperMapsAConnectOAuthRefusal(TestCase):
    """F-2: ``stripe.OAuth.token`` now goes through the wrapper, so its own
    error class must map — to a non-retryable fatal, like every other
    authorisation/configuration refusal."""

    def test_oauth_error_is_a_fatal(self):
        err = stripe.oauth_error.InvalidGrantError(
            "invalid_grant", "Authorization code already used")
        self.assertIsInstance(err, stripe.oauth_error.OAuthError)
        mock_fn = MagicMock(side_effect=err)
        with self.assertRaises(StripeFatalError):
            stripe_call(mock_fn, api_key="sk_test_x", retryable=True, idempotency_key="k")
        self.assertEqual(mock_fn.call_count, 1)  # never retried


class StripeCallWrapperTest(TestCase):
    def test_successful_call(self):
        mock_fn = MagicMock(return_value="result")
        result = stripe_call(mock_fn, api_key="sk_test_x", arg1="val1")
        self.assertEqual(result, "result")
        mock_fn.assert_called_once_with(api_key="sk_test_x", arg1="val1")

    def test_rate_limit_raises_transient(self):
        mock_fn = MagicMock(side_effect=stripe.error.RateLimitError("rate limited"))
        with self.assertRaises(StripeTransientError):
            stripe_call(mock_fn, api_key="sk_test_x", retryable=False)

    def test_card_error_raises_payment_error(self):
        err = stripe.error.CardError("declined", "param", "card_declined")
        mock_fn = MagicMock(side_effect=err)
        with self.assertRaises(StripePaymentError):
            stripe_call(mock_fn, api_key="sk_test_x")

    def test_auth_error_raises_fatal(self):
        mock_fn = MagicMock(side_effect=stripe.error.AuthenticationError("bad key"))
        with self.assertRaises(StripeFatalError):
            stripe_call(mock_fn, api_key="sk_test_x")

    def test_idempotency_error_raises_fatal(self):
        mock_fn = MagicMock(side_effect=stripe.error.IdempotencyError("mismatch"))
        with self.assertRaises(StripeFatalError):
            stripe_call(mock_fn, api_key="sk_test_x")

    @patch("apps.billing.stripe.services.stripe_service.time.sleep")
    def test_retryable_with_idempotency_key_retries(self, mock_sleep):
        mock_fn = MagicMock(
            side_effect=[
                stripe.error.APIConnectionError("timeout"),
                "success",
            ]
        )
        result = stripe_call(mock_fn, api_key="sk_test_x", retryable=True, idempotency_key="key-1", max_retries=2)
        self.assertEqual(result, "success")
        self.assertEqual(mock_fn.call_count, 2)

    def test_retryable_without_key_does_not_retry(self):
        mock_fn = MagicMock(side_effect=stripe.error.APIConnectionError("timeout"))
        with self.assertRaises(StripeTransientError):
            stripe_call(mock_fn, api_key="sk_test_x", retryable=True, idempotency_key=None)
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


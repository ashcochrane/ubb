"""Clerk member-token verification (identity build 1, #79).

Exercises the real ``jwt.decode`` path via HS256 (the dev/test mode) — no
network, no ``cryptography``. The RS256/JWKS production adapter is config-driven
and delegates signature checking to PyJWT; it is not exercised here because it
requires a live JWKS and the crypto backend.
"""
import time

import jwt
from django.test import SimpleTestCase, override_settings

from core.clerk_auth import verify_member_token

SECRET = "test-clerk-hs256-secret-32bytes-minimum-length"
ISSUER = "https://clerk.test.example"


def _token(secret=SECRET, issuer=ISSUER, exp_delta=900, **claims):
    payload = {"iss": issuer, "sub": "user_abc", "email": "sam@example.com",
               "exp": int(time.time()) + exp_delta}
    payload.update(claims)
    return jwt.encode(payload, secret, algorithm="HS256")


@override_settings(CLERK_ISSUER=ISSUER, CLERK_HS256_SECRET=SECRET,
                   CLERK_JWKS_URL="", CLERK_JWT_PUBLIC_KEY="")
class HS256ModeTest(SimpleTestCase):
    def test_valid_token_returns_claims(self):
        claims = verify_member_token(_token())
        self.assertIsNotNone(claims)
        self.assertEqual(claims["sub"], "user_abc")
        self.assertEqual(claims["email"], "sam@example.com")

    def test_expired_token_rejected(self):
        self.assertIsNone(verify_member_token(_token(exp_delta=-10)))

    def test_token_missing_exp_rejected(self):
        # `require: [exp]` — a token with no expiry is never accepted.
        payload = {"iss": ISSUER, "sub": "x", "email": "x@example.com"}
        token = jwt.encode(payload, SECRET, algorithm="HS256")
        self.assertIsNone(verify_member_token(token))

    def test_wrong_secret_rejected(self):
        self.assertIsNone(verify_member_token(_token(secret="not-the-secret")))

    def test_wrong_issuer_rejected(self):
        self.assertIsNone(verify_member_token(_token(issuer="https://evil.example")))

    def test_garbage_token_rejected(self):
        self.assertIsNone(verify_member_token("not.a.jwt"))
        self.assertIsNone(verify_member_token(""))
        self.assertIsNone(verify_member_token(None))


@override_settings(CLERK_ISSUER="", CLERK_HS256_SECRET="",
                   CLERK_JWKS_URL="", CLERK_JWT_PUBLIC_KEY="")
class DisabledWhenUnconfiguredTest(SimpleTestCase):
    def test_no_config_means_every_token_is_none(self):
        # Member auth OFF: even a well-formed token cannot authenticate.
        self.assertIsNone(verify_member_token(_token()))


@override_settings(CLERK_ISSUER=ISSUER, CLERK_JWT_PUBLIC_KEY="-----BEGIN PUBLIC KEY-----\nx\n-----END PUBLIC KEY-----",
                   CLERK_HS256_SECRET=SECRET, CLERK_JWKS_URL="")
class RS256WinsOverHS256Test(SimpleTestCase):
    def test_hs256_token_rejected_when_rs256_key_configured(self):
        # A public key is configured => RS256 mode. An HS256 token (even signed
        # with the shared secret) must not verify — no algorithm downgrade.
        self.assertIsNone(verify_member_token(_token()))

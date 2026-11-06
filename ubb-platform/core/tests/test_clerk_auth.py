"""Clerk member-token verification (identity build 1, #79).

Exercises the real ``jwt.decode`` path via HS256 (the dev/test mode) — no
network. The RS256 production adapter is exercised too, since R10 Stage C5
(F-16, RULED Q16): a PEM pinned in config and a JWKS answered by an in-test
fake, both over an RSA key generated in the test — no Clerk account, no
network — through the ``cryptography`` backend the lock now pins. Those
tests FAIL where ``cryptography`` is absent (PyJWT then raises
``InvalidAlgorithmError`` for RS256), which is the point: they are proven in a
clean isolated environment holding exactly the lock, and a control run there
with ``cryptography`` uninstalled fails them.
"""
import logging
import time
from unittest.mock import patch

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


# ---------------------------------------------------------------------------
# The production path, RS256 (R10 Stage C5, F-16, RULED Q16).
#
# An RSA key pair generated IN the test — no Clerk account, no network — signs
# a session token; the PEM mode pins its public key in config, the JWKS mode
# answers it from a fake JWKS keyed by `kid`. Both need the `cryptography`
# backend PyJWT's RS256 rides on, which `requirements.lock.txt` pins since C5:
# without it PyJWT refuses the algorithm (`InvalidAlgorithmError`), the PEM
# path answers `None`, and these tests FAIL — the control run in the clean
# isolated environment with `cryptography` uninstalled shows exactly that.
# ---------------------------------------------------------------------------

KID = "kid-c5-test"


def _rsa_key_pair():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()).decode()
    public_pem = private.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return private_pem, public_pem


def _rs256_token(private_pem, issuer=ISSUER, exp_delta=900, kid=KID, **claims):
    payload = {"iss": issuer, "sub": "user_rs256", "email": "rs@example.com",
               "exp": int(time.time()) + exp_delta}
    payload.update(claims)
    return jwt.encode(payload, private_pem, algorithm="RS256",
                      headers={"kid": kid} if kid else None)


class RS256PemModeTest(SimpleTestCase):
    """`CLERK_JWT_PUBLIC_KEY`: a PEM pinned in config verifies an RS256 token."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.private_pem, cls.public_pem = _rsa_key_pair()

    def _settings(self):
        return override_settings(
            CLERK_ISSUER=ISSUER, CLERK_JWT_PUBLIC_KEY=self.public_pem,
            CLERK_HS256_SECRET="", CLERK_JWKS_URL="")

    def test_a_token_signed_by_the_pinned_keys_private_half_verifies(self):
        with self._settings():
            claims = verify_member_token(_rs256_token(self.private_pem))
        self.assertIsNotNone(claims, "RS256 PEM verification answered None — "
                             "is the cryptography backend installed?")
        self.assertEqual(claims["sub"], "user_rs256")
        self.assertEqual(claims["email"], "rs@example.com")

    def test_a_token_signed_by_another_key_is_rejected(self):
        other_private, _ = _rsa_key_pair()
        with self._settings():
            self.assertIsNone(verify_member_token(_rs256_token(other_private)))

    def test_an_expired_or_wrong_issuer_rs256_token_is_rejected(self):
        with self._settings():
            self.assertIsNone(verify_member_token(
                _rs256_token(self.private_pem, exp_delta=-10)))
            self.assertIsNone(verify_member_token(
                _rs256_token(self.private_pem, issuer="https://evil.example")))

    def test_a_missing_rs256_backend_fails_closed_and_says_so(self):
        """The defect F-16 names: PyJWT without `cryptography` raises
        `InvalidAlgorithmError` for RS256, which the seam swallowed into a
        silent 401. It still fails closed, and now logs a structured warning
        naming the backend — a deployment defect, not a caller's."""
        with self._settings(), \
                patch("core.clerk_auth.jwt.decode",
                      side_effect=jwt.exceptions.InvalidAlgorithmError(
                          "Algorithm not supported")), \
                self.assertLogs("ubb.auth", "WARNING") as logs:
            self.assertIsNone(verify_member_token(_rs256_token(self.private_pem)))
        self.assertEqual([r.getMessage() for r in logs.records],
                         ["clerk.rs256_backend_unavailable"])
        self.assertEqual(logs.records[0].data["algorithms"], ["RS256"])


class RS256JwksModeTest(SimpleTestCase):
    """`CLERK_JWKS_URL`: the signing key is read from a JWKS, answered here by
    a fake — `PyJWKClient.fetch_data` is replaced, so nothing is fetched."""

    JWKS_URL = "https://clerk.test.example/.well-known/jwks.json"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.private_pem, cls.public_pem = _rsa_key_pair()
        jwk = jwt.algorithms.RSAAlgorithm.to_jwk(
            jwt.algorithms.RSAAlgorithm(jwt.algorithms.RSAAlgorithm.SHA256)
            .prepare_key(cls.public_pem), as_dict=True)
        cls.jwks = {"keys": [{**jwk, "kid": KID, "use": "sig", "alg": "RS256"}]}

    def setUp(self):
        # The seam caches one client per URL; a fresh fake per test.
        from core import clerk_auth
        clerk_auth._jwks_clients.pop(self.JWKS_URL, None)
        self.addCleanup(clerk_auth._jwks_clients.pop, self.JWKS_URL, None)

    def _settings(self):
        return override_settings(
            CLERK_ISSUER=ISSUER, CLERK_JWKS_URL=self.JWKS_URL,
            CLERK_HS256_SECRET="", CLERK_JWT_PUBLIC_KEY="")

    def test_a_token_whose_kid_the_jwks_answers_verifies(self):
        with self._settings(), \
                patch("jwt.jwks_client.PyJWKClient.fetch_data", return_value=self.jwks):
            claims = verify_member_token(_rs256_token(self.private_pem))
        self.assertIsNotNone(claims, "RS256 JWKS verification answered None — "
                             "is the cryptography backend installed?")
        self.assertEqual(claims["sub"], "user_rs256")

    def test_a_kid_the_jwks_does_not_hold_is_rejected_loudly(self):
        with self._settings(), \
                patch("jwt.jwks_client.PyJWKClient.fetch_data", return_value=self.jwks), \
                self.assertLogs("ubb.auth", "WARNING") as logs:
            self.assertIsNone(verify_member_token(
                _rs256_token(self.private_pem, kid="kid-unknown")))
        self.assertIn("clerk.verification_key_unavailable",
                      [r.getMessage() for r in logs.records])

    def test_a_token_signed_by_another_key_is_rejected(self):
        other_private, _ = _rsa_key_pair()
        with self._settings(), \
                patch("jwt.jwks_client.PyJWKClient.fetch_data", return_value=self.jwks):
            self.assertIsNone(verify_member_token(_rs256_token(other_private)))

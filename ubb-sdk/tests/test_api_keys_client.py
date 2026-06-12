import unittest
from unittest.mock import MagicMock

from ubb.client import UBBClient

LIST_FIXTURE = {
    "data": [{
        "id": "11111111-2222-3333-4444-555555555555",
        "key_prefix": "ubb_live_abc1234",
        "label": "primary",
        "is_active": True,
        "last_used_at": None,
        "created_at": "2026-06-12T00:00:00+00:00",
    }],
}

CREATED_FIXTURE = {
    "id": "11111111-2222-3333-4444-555555555555",
    "key_prefix": "ubb_live_new1234",
    "label": "ci",
    "tenant_id": "99999999-8888-7777-6666-555555555555",
    "api_key": "ubb_live_new1234rawsecret",
}

ROTATED_FIXTURE = {
    "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    "key_prefix": "ubb_live_rot1234",
    "label": "primary (rotated)",
    "revoked_key_id": "11111111-2222-3333-4444-555555555555",
    "api_key": "ubb_live_rot1234rawsecret",
}

REVOKED_FIXTURE = {"id": "11111111-2222-3333-4444-555555555555", "is_active": False}

KEY_ID = "11111111-2222-3333-4444-555555555555"


class ApiKeysClientTest(unittest.TestCase):
    def _client_with_mock_request(self, fixture):
        ubb = UBBClient(api_key="ubb_live_t", metering=True)
        ubb.metering._request = MagicMock(
            return_value=MagicMock(status_code=200, json=lambda: fixture)
        )
        return ubb

    def test_list_api_keys_hits_correct_url(self):
        ubb = self._client_with_mock_request(LIST_FIXTURE)
        result = ubb.list_api_keys()
        ubb.metering._request.assert_called_once_with(
            "get", "/api/v1/tenant/api-keys"
        )
        self.assertEqual(result, LIST_FIXTURE)
        ubb.close()

    def test_create_api_key_posts_label_and_mode(self):
        ubb = self._client_with_mock_request(CREATED_FIXTURE)
        result = ubb.create_api_key(label="ci", is_test=False)
        ubb.metering._request.assert_called_once_with(
            "post", "/api/v1/tenant/api-keys",
            json={"label": "ci", "is_test": False},
        )
        self.assertTrue(result["api_key"].startswith("ubb_live_"))
        ubb.close()

    def test_create_api_key_defaults(self):
        ubb = self._client_with_mock_request(CREATED_FIXTURE)
        ubb.create_api_key()
        ubb.metering._request.assert_called_once_with(
            "post", "/api/v1/tenant/api-keys",
            json={"label": "", "is_test": False},
        )
        ubb.close()

    def test_rotate_api_key_posts_to_rotate_path(self):
        ubb = self._client_with_mock_request(ROTATED_FIXTURE)
        result = ubb.rotate_api_key(KEY_ID)
        ubb.metering._request.assert_called_once_with(
            "post", f"/api/v1/tenant/api-keys/{KEY_ID}/rotate", json={}
        )
        self.assertEqual(result["revoked_key_id"], KEY_ID)
        self.assertTrue(result["api_key"].startswith("ubb_live_"))
        ubb.close()

    def test_revoke_api_key_deletes(self):
        ubb = self._client_with_mock_request(REVOKED_FIXTURE)
        result = ubb.revoke_api_key(KEY_ID)
        ubb.metering._request.assert_called_once_with(
            "delete", f"/api/v1/tenant/api-keys/{KEY_ID}"
        )
        self.assertEqual(result, REVOKED_FIXTURE)
        ubb.close()

    def test_api_key_methods_require_metering(self):
        from ubb.exceptions import UBBError

        ubb = UBBClient(api_key="ubb_live_t", metering=False)
        for call in (ubb.list_api_keys,
                     lambda: ubb.create_api_key(label="x"),
                     lambda: ubb.rotate_api_key(KEY_ID),
                     lambda: ubb.revoke_api_key(KEY_ID)):
            with self.assertRaises(UBBError):
                call()


if __name__ == "__main__":
    unittest.main()

import unittest
from unittest.mock import MagicMock

from ubb.client import UBBClient

CREATE_FIXTURE = {
    "sandbox_tenant_id": "11111111-2222-3333-4444-555555555555",
    "api_key": "ubb_test_abc123",
}

STATUS_FIXTURE = {
    "exists": True,
    "sandbox_tenant_id": "11111111-2222-3333-4444-555555555555",
    "key_prefixes": ["ubb_test_abc123"[:16]],
}


class SandboxClientTest(unittest.TestCase):
    def _client_with_mock_request(self, fixture):
        ubb = UBBClient(api_key="ubb_live_t", metering=True)
        ubb.metering._request = MagicMock(
            return_value=MagicMock(status_code=200, json=lambda: fixture)
        )
        return ubb

    def test_create_sandbox_posts_and_returns_raw_test_key(self):
        ubb = self._client_with_mock_request(CREATE_FIXTURE)
        result = ubb.create_sandbox()
        ubb.metering._request.assert_called_once_with(
            "post", "/api/v1/tenant/sandbox", json={}
        )
        self.assertEqual(result, CREATE_FIXTURE)
        self.assertTrue(result["api_key"].startswith("ubb_test_"))
        ubb.close()

    def test_get_sandbox_hits_correct_url(self):
        ubb = self._client_with_mock_request(STATUS_FIXTURE)
        result = ubb.get_sandbox()
        ubb.metering._request.assert_called_once_with(
            "get", "/api/v1/tenant/sandbox"
        )
        self.assertEqual(result, STATUS_FIXTURE)
        ubb.close()

    def test_sandbox_methods_require_metering(self):
        from ubb.exceptions import UBBError

        ubb = UBBClient(api_key="ubb_live_t", metering=False)
        with self.assertRaises(UBBError):
            ubb.create_sandbox()
        with self.assertRaises(UBBError):
            ubb.get_sandbox()


if __name__ == "__main__":
    unittest.main()

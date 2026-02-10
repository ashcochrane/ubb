from unittest.mock import patch, MagicMock

from django.test import TestCase, Client


class HealthEndpointTest(TestCase):
    def setUp(self):
        self.client = Client()

    def test_health_returns_200(self):
        response = self.client.get("/api/v1/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_health_no_auth_required(self):
        # No Authorization header — should still return 200
        response = self.client.get("/api/v1/health")
        self.assertEqual(response.status_code, 200)


class ReadyEndpointTest(TestCase):
    def setUp(self):
        self.client = Client()

    def test_ready_returns_200_when_all_ok(self):
        mock_redis = MagicMock()
        mock_redis.ping.return_value = True
        with patch("api.v1.endpoints.redis.from_url", return_value=mock_redis):
            response = self.client.get("/api/v1/ready")
            body = response.json()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(body["status"], "ready")
            self.assertEqual(body["checks"]["database"], "ok")
            self.assertEqual(body["checks"]["redis"], "ok")

    def test_ready_no_auth_required(self):
        response = self.client.get("/api/v1/ready")
        self.assertIn(response.status_code, [200, 503])

    def test_ready_returns_503_when_db_fails(self):
        with patch("django.db.connection.ensure_connection", side_effect=Exception("db down")):
            response = self.client.get("/api/v1/ready")
            body = response.json()
            self.assertEqual(body["checks"]["database"], "error")
            self.assertEqual(body["status"], "not_ready")
            self.assertEqual(response.status_code, 503)

    def test_ready_returns_503_when_redis_fails(self):
        mock_redis = MagicMock()
        mock_redis.ping.side_effect = Exception("redis down")
        with patch("redis.from_url", return_value=mock_redis):
            response = self.client.get("/api/v1/ready")
            body = response.json()
            self.assertEqual(body["checks"]["redis"], "error")
            self.assertEqual(body["status"], "not_ready")
            self.assertEqual(response.status_code, 503)

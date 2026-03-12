from __future__ import annotations

import unittest
from unittest.mock import patch

try:
    from fastapi.testclient import TestClient
except Exception:  # pragma: no cover
    TestClient = None

from cryptobot.webapp import create_app


class _FakeStore:
    def get_user_by_id(self, user_id: int):
        return {"id": user_id, "email": "admin@example.com", "is_active": 1, "is_admin": 1}


class _FakeSvc:
    def __init__(self):
        self.store = _FakeStore()

    def login_email(self, email: str, password: str):
        if email == "admin@example.com" and password == "password123":
            return {"id": 1, "email": email, "is_admin": 1}
        return None

    def get_preferred_activation_key(self, user_id: int):
        return None

    def is_admin_user(self, user_id: int) -> bool:
        return int(user_id) == 1

    def validate_key_for_user_device(self, user_id: int, activation_key: str, device_id: str) -> bool:
        return False


@unittest.skipIf(TestClient is None, "httpx/testclient not installed in environment")
class WebappAdminBypassTests(unittest.TestCase):
    @patch("cryptobot.webapp.generate_live_prediction", return_value={"ok": True, "confidence": 0.7})
    @patch("cryptobot.webapp._svc", return_value=_FakeSvc())
    def test_admin_predict_bypasses_license_key(self, _svc, _predict):
        app = create_app()
        client = TestClient(app)

        login = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "password123"})
        self.assertEqual(login.status_code, 200)

        res = client.post("/api/predict", json={"market_type": "crypto", "exchange": "binance", "symbol": "BTC/USDT", "timeframe": "1h"})
        self.assertEqual(res.status_code, 200)

    @patch("cryptobot.webapp._svc", return_value=_FakeSvc())
    def test_admin_license_status_reports_active_without_key(self, _svc):
        app = create_app()
        client = TestClient(app)

        login = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "password123"})
        self.assertEqual(login.status_code, 200)

        res = client.get("/api/license/status")
        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertTrue(payload.get("active"))
        self.assertTrue(payload.get("admin_bypass"))


if __name__ == "__main__":
    unittest.main()

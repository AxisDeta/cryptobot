from __future__ import annotations

import unittest
from unittest.mock import patch

from cryptobot.config import BotSettings
from cryptobot.licensing.security import hash_password
from cryptobot.licensing.service import LicensingService


class _BackfillStore:
    def __init__(self, _settings):
        self.user = {
            "id": 11,
            "email": "user@example.com",
            "is_active": 1,
            "password_hash": hash_password("password123"),
        }
        self._licenses = []
        self.created_payment = 0
        self.activated_count = 0

    def ensure_schema(self):
        return None

    def get_user_by_email(self, email: str):
        return self.user if email == "user@example.com" else None

    def list_user_licenses(self, user_id: int, limit: int = 1):
        return list(self._licenses)[:limit]

    def create_payment(self, **_kwargs):
        self.created_payment += 1
        return 501

    def create_license(self, **_kwargs):
        self._licenses = [{"id": 1, "status": "issued", "activation_key": "CTB-TRIAL"}]
        return 701

    def activate_license(self, license_id: int, device_id: str, activated_at, expires_at):
        self.activated_count += 1
        self._licenses = [{"id": int(license_id), "status": "active", "activation_key": "CTB-TRIAL"}]


class TrialBackfillTests(unittest.TestCase):
    @patch("cryptobot.licensing.service.send_activation_key_email", return_value=True)
    @patch("cryptobot.licensing.service.LicensingStore", _BackfillStore)
    def test_login_grants_trial_for_existing_user_without_license(self, _email):
        svc = LicensingService(BotSettings())
        user = svc.login_email("user@example.com", "password123")
        self.assertIsNotNone(user)
        self.assertEqual(svc.store.created_payment, 1)
        self.assertEqual(svc.store.activated_count, 1)

    @patch("cryptobot.licensing.service.send_activation_key_email", return_value=True)
    @patch("cryptobot.licensing.service.LicensingStore", _BackfillStore)
    def test_login_does_not_duplicate_trial_when_license_exists(self, _email):
        svc = LicensingService(BotSettings())
        svc.store._licenses = [{"id": 9, "status": "active"}]
        user = svc.login_email("user@example.com", "password123")
        self.assertIsNotNone(user)
        self.assertEqual(svc.store.created_payment, 0)


if __name__ == "__main__":
    unittest.main()

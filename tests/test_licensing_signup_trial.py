from __future__ import annotations

import unittest
from unittest.mock import patch

from cryptobot.config import BotSettings
from cryptobot.licensing.service import LicensingService


class _FakeStore:
    def __init__(self, _settings):
        self.user_id = 7
        self.created_payment = None
        self.created_license = None
        self.activated = None

    def ensure_schema(self):
        return None

    def get_user_by_email(self, _email: str):
        return None

    def create_user(self, **_kwargs):
        return self.user_id

    def create_email_verification(self, **_kwargs):
        return None

    def create_payment(self, **kwargs):
        self.created_payment = kwargs
        return 13

    def create_license(self, **kwargs):
        self.created_license = kwargs
        return 21

    def activate_license(self, license_id: int, device_id: str, activated_at, expires_at):
        self.activated = {
            "license_id": license_id,
            "device_id": device_id,
            "activated_at": activated_at,
            "expires_at": expires_at,
        }


class SignupTrialTests(unittest.TestCase):
    @patch("cryptobot.licensing.service.send_activation_key_email", return_value=True)
    @patch("cryptobot.licensing.service.send_verification_email", return_value=True)
    @patch("cryptobot.licensing.service.LicensingStore", _FakeStore)
    def test_signup_returns_trial_activation_key(self, _mock_verify, _mock_trial_email):
        svc = LicensingService(BotSettings())

        result = svc.signup_email("test@example.com", "password123")

        self.assertEqual(result["user_id"], 7)
        self.assertEqual(result["trial_duration_days"], 1)
        self.assertTrue(str(result["trial_activation_key"]).startswith("CTB-"))
        self.assertEqual(svc.store.created_payment["provider"], "trial")
        self.assertEqual(svc.store.created_payment["amount_cents"], 0)
        self.assertEqual(svc.store.created_license["plan_code"], "trial_1d")
        self.assertEqual(svc.store.created_license["duration_days"], 1)
        self.assertEqual(svc.store.activated["device_id"], "account_trial")


if __name__ == "__main__":
    unittest.main()

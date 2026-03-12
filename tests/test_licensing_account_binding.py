from __future__ import annotations

import unittest
from datetime import timedelta
from unittest.mock import patch

from cryptobot.config import BotSettings
from cryptobot.licensing.security import utcnow
from cryptobot.licensing.service import LicensingService


class _StoreForAccountBinding:
    def __init__(self, _settings):
        self.license_row = {
            "id": 99,
            "user_id": 7,
            "status": "active",
            "expires_at": utcnow().replace(tzinfo=None) + timedelta(days=1),
            "bound_device_id": "device-A",
            "plan_code": "monthly",
        }

    def ensure_schema(self):
        return None

    def get_license_by_key_hash(self, _key_hash: str):
        return dict(self.license_row)


class _StoreActivateActive:
    def __init__(self, _settings):
        self.license_row = {
            "id": 77,
            "user_id": 7,
            "status": "active",
            "expires_at": utcnow().replace(tzinfo=None) + timedelta(days=2),
            "bound_device_id": "device-A",
            "plan_code": "monthly",
        }

    def ensure_schema(self):
        return None

    def get_license_by_key_hash(self, _key_hash: str):
        return dict(self.license_row)


class AccountBindingTests(unittest.TestCase):
    @patch("cryptobot.licensing.service.LicensingStore", _StoreForAccountBinding)
    def test_validate_key_allows_different_device_for_same_user(self):
        svc = LicensingService(BotSettings())
        ok = svc.validate_key_for_user_device(7, "CTB-AAAA-BBBB-CCCC-DDDD", "device-B")
        self.assertTrue(ok)

    @patch("cryptobot.licensing.service.LicensingStore", _StoreActivateActive)
    def test_activate_does_not_reject_when_active_key_used_on_another_device(self):
        svc = LicensingService(BotSettings())
        result = svc.activate_key_for_user(7, "CTB-AAAA-BBBB-CCCC-DDDD", "device-B")
        self.assertEqual(result["status"], "active")


if __name__ == "__main__":
    unittest.main()

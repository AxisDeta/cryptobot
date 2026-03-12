from __future__ import annotations

import unittest
from datetime import timedelta
from unittest.mock import patch

from cryptobot.config import BotSettings
from cryptobot.licensing.security import hash_value, utcnow
from cryptobot.licensing.service import LicensingService


class _ExpiryStore:
    def __init__(self, _settings):
        now = utcnow().replace(tzinfo=None)
        self.expired_called = 0
        self.license_row = {
            "user_id": 9,
            "status": "active",
            "expires_at": now - timedelta(seconds=5),
        }

    def ensure_schema(self):
        return None

    def expire_active_licenses(self, _now):
        self.expired_called += 1
        self.license_row["status"] = "expired"

    def get_license_by_key_hash(self, _hash):
        return self.license_row


class TrialExpiryTests(unittest.TestCase):
    @patch("cryptobot.licensing.service.LicensingStore", _ExpiryStore)
    def test_validate_key_rejects_after_expiry_and_sweeps(self):
        svc = LicensingService(BotSettings())
        valid = svc.validate_key_for_user_device(9, "CTB-TEST", "dev1")
        self.assertFalse(valid)
        self.assertEqual(svc.store.expired_called, 1)


if __name__ == "__main__":
    unittest.main()

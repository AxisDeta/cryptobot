from __future__ import annotations

import unittest
from unittest.mock import patch

from cryptobot.config import BotSettings
from cryptobot.licensing.service import LicensingService


class _SignalStore:
    def __init__(self, _settings):
        self.created = []

    def ensure_schema(self):
        return None

    def signal_outcomes_analytics(self):
        return {
            "counts": {"win": 4, "loss": 2, "skip": 1, "pending": 3},
            "total": 10,
            "users_with_signals": 2,
            "avg_per_user": {"win": 2.0, "loss": 1.0, "skip": 0.5, "pending": 1.5},
        }

    def create_signal_outcome(self, **kwargs):
        self.created.append(kwargs)
        return 88

    def update_signal_outcome(self, signal_id: int, user_id: int, outcome: str):
        return signal_id == 88 and user_id == 5 and outcome == "win"


class SignalAnalyticsTests(unittest.TestCase):
    @patch("cryptobot.licensing.service.LicensingStore", _SignalStore)
    def test_analytics_contains_percentages(self):
        svc = LicensingService(BotSettings())
        data = svc.signal_outcomes_analytics()
        self.assertEqual(data["percentages"]["win"], 40.0)
        self.assertEqual(data["percentages"]["pending"], 30.0)

    @patch("cryptobot.licensing.service.LicensingStore", _SignalStore)
    def test_create_and_update_signal_outcome(self):
        svc = LicensingService(BotSettings())
        signal_id = svc.create_signal_outcome(5, "BTC/USDT", "1h", "BUY", 0.71)
        self.assertEqual(signal_id, 88)
        self.assertTrue(svc.update_signal_outcome(signal_id, 5, "win"))


if __name__ == "__main__":
    unittest.main()

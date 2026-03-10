from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from cryptobot.live import build_training_set, select_high_impact_posts
from cryptobot.schemas import OHLCVBar, SentimentPost


class LiveTests(unittest.TestCase):
    def _bars(self) -> list[OHLCVBar]:
        base = datetime(2025, 1, 1)
        prices = [100 + i * 0.5 + (1 if i % 5 == 0 else 0) for i in range(40)]
        return [
            OHLCVBar(base + timedelta(hours=i), p, p + 1, p - 1, p, 100 + i)
            for i, p in enumerate(prices)
        ]

    def test_select_high_impact_posts(self) -> None:
        now = datetime(2025, 1, 1)
        posts = [
            SentimentPost(now, "reddit", "a", "b", 10, 5),
            SentimentPost(now, "reddit", "a", "b", 100, 20),
        ]
        selected = select_high_impact_posts(posts, min_engagement=50)
        self.assertEqual(len(selected), 1)

    def test_build_training_set(self) -> None:
        bars = self._bars()
        posts = [SentimentPost(bars[0].ts, "reddit", "BTC bullish", "buy", 20, 10)]
        X, y, vols = build_training_set(bars, posts, min_history=30)
        self.assertEqual(len(X), len(y))
        self.assertEqual(len(y), len(vols))
        self.assertGreater(len(X), 0)


if __name__ == "__main__":
    unittest.main()

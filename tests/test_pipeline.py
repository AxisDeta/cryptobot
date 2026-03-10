from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from cryptobot.config import BotSettings
from cryptobot.pipeline import HybridTradingBot
from cryptobot.schemas import OHLCVBar, SentimentPost


class PipelineTests(unittest.TestCase):
    def _bars(self) -> list[OHLCVBar]:
        base = datetime(2025, 1, 1)
        prices = [100, 101, 102, 101, 103, 104, 105, 104, 106, 107, 108, 109]
        return [
            OHLCVBar(base + timedelta(hours=i), p, p + 1, p - 1, p, 1000 + 3 * i)
            for i, p in enumerate(prices)
        ]

    def _posts(self) -> list[SentimentPost]:
        base = datetime(2025, 1, 1)
        return [
            SentimentPost(base, "reddit", "BTC bullish", "adoption buy", 50, 30),
            SentimentPost(base, "reddit", "macro uncertain", "neutral", 10, 3),
            SentimentPost(base, "reddit", "minor hack rumor", "bearish", 5, 2),
        ]

    def test_train_and_recommend(self) -> None:
        settings = BotSettings(confidence_threshold=0.1)
        bot = HybridTradingBot(settings)

        # Training uses the same feature shape produced by infer_snapshot.
        train_X = [
            [0.01, 0.02, 0.2, 0.03, 0.1, 0.02, 0.01, 0.10, 0.004, 0.006, 0.20, -0.01, 0.2, 0.05, 0.1, 0.6, 0.1, 0.04, 0.004],
            [-0.01, 0.03, -0.4, -0.02, -0.1, -0.03, -0.02, -0.12, 0.006, 0.009, -0.35, -0.03, -0.2, -0.03, 0.2, 0.2, 0.4, 0.08, -0.006],
            [0.02, 0.02, 0.1, 0.01, 0.05, 0.03, 0.02, 0.14, 0.003, 0.005, 0.30, -0.01, 0.3, 0.01, 0.1, 0.7, 0.1, 0.03, 0.006],
            [-0.02, 0.04, -0.1, -0.03, -0.2, -0.02, -0.01, -0.08, 0.007, 0.011, -0.28, -0.04, -0.3, -0.04, 0.2, 0.1, 0.5, 0.03, -0.012],
        ]
        y = [1, 0, 1, 0]
        vols = [0.01, 0.02, 0.03, 0.04, 0.025, 0.015]
        bot.train(train_X, y, vols)

        pos = bot.recommend_position(self._bars(), self._posts())
        self.assertTrue(-2.0 <= pos <= 2.0)


if __name__ == "__main__":
    unittest.main()


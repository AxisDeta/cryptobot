from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from cryptobot.features.market import compute_market_features
from cryptobot.features.sentiment import compute_sentiment_features
from cryptobot.schemas import OHLCVBar, SentimentPost


class FeatureTests(unittest.TestCase):
    def test_market_features(self) -> None:
        base = datetime(2025, 1, 1)
        bars = [
            OHLCVBar(base + timedelta(hours=i), 100 + i, 101 + i, 99 + i, 100 + i, 10 + i)
            for i in range(10)
        ]
        feats = compute_market_features(bars)
        self.assertIn("rolling_volatility", feats)
        self.assertIn("volume_zscore", feats)

    def test_sentiment_features(self) -> None:
        base = datetime(2025, 1, 1)
        posts = [
            SentimentPost(base, "reddit", "BTC bullish adoption", "buy", 20, 10),
            SentimentPost(base, "reddit", "possible hack risk", "bearish", 5, 3),
        ]
        feats = compute_sentiment_features(posts)
        self.assertGreater(feats["sentiment_volatility"], 0.0)


if __name__ == "__main__":
    unittest.main()

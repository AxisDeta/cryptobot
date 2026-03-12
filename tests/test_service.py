from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from cryptobot.config import BotSettings
from cryptobot.schemas import OHLCVBar, OrderBookSnapshot, SentimentPost
from cryptobot.service import LivePredictionRequest, generate_live_prediction


class _FakeMarketClient:
    def __init__(self, _exchange: str) -> None:
        pass

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 240):
        base = datetime(2025, 1, 1)
        prices = [100 + (i * 0.2) + (1 if i % 9 == 0 else 0) for i in range(limit)]
        return [
            OHLCVBar(base + timedelta(hours=i), p, p + 1, p - 1, p, 1000 + i)
            for i, p in enumerate(prices)
        ]

    def fetch_order_book_imbalance(self, symbol: str, depth: int = 20):
        return OrderBookSnapshot(datetime(2025, 1, 1), 100.0, 90.0)


class _FakeForexClient:
    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 240):
        base = datetime(2025, 1, 1)
        prices = [1.10 + (i * 0.0002) + (0.0005 if i % 11 == 0 else 0.0) for i in range(limit)]
        return [
            OHLCVBar(base + timedelta(hours=i), p, p + 0.0007, p - 0.0007, p, 0.0)
            for i, p in enumerate(prices)
        ]

    def fetch_order_book_imbalance(self, symbol: str, depth: int = 20):
        return OrderBookSnapshot(datetime(2025, 1, 1), 0.0, 0.0)




class _FailingCryptoClient:
    def __init__(self, _exchange: str) -> None:
        pass

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 240):
        raise RuntimeError("ccxt unavailable")

    def fetch_order_book_imbalance(self, symbol: str, depth: int = 20):
        raise RuntimeError("ccxt unavailable")



class ServiceTests(unittest.TestCase):
    @patch("cryptobot.service.CCXTMarketDataClient", _FakeMarketClient)
    @patch("cryptobot.service.load_reddit_posts")
    def test_generate_live_prediction(self, mock_reddit):
        mock_reddit.return_value = [
            SentimentPost(datetime(2025, 1, 1), "reddit", "BTC bullish", "buy", 50, 20)
        ]
        settings = BotSettings()
        req = LivePredictionRequest(ohlcv_limit=80, reddit_limit=10)
        result = generate_live_prediction(settings, req)
        self.assertIn("recommended_position", result)
        self.assertIn("confidence", result)
        self.assertEqual(result.get("market_type"), "crypto")


    @patch("cryptobot.service.CCXTMarketDataClient", _FailingCryptoClient)
    @patch("cryptobot.service._fetch_crypto_via_yfinance")
    @patch("cryptobot.service.load_reddit_posts")
    def test_generate_live_prediction_crypto_ccxt_fallback_to_yfinance(self, mock_reddit, mock_fallback):
        mock_reddit.return_value = []
        base = datetime(2025, 1, 1)
        mock_fallback.return_value = [
            OHLCVBar(base + timedelta(hours=i), 100 + i, 101 + i, 99 + i, 100 + i, 1000 + i)
            for i in range(80)
        ]
        settings = BotSettings()
        req = LivePredictionRequest(market_type="crypto", symbol="BTC/USDT", timeframe="1h", ohlcv_limit=80)
        result = generate_live_prediction(settings, req)
        self.assertEqual(result.get("market_type"), "crypto")
        self.assertIn("confidence", result)
        mock_fallback.assert_called_once()

    @patch("cryptobot.service.ForexMarketDataClient", _FakeForexClient)
    def test_generate_live_prediction_forex(self):
        settings = BotSettings(symbol="BTC/USDT")
        req = LivePredictionRequest(market_type="forex", symbol="eurusd", timeframe="1h", ohlcv_limit=90)
        result = generate_live_prediction(settings, req)
        self.assertEqual(result.get("market_type"), "forex")
        self.assertEqual(result.get("symbol"), "EUR/USD")
        self.assertIn("model_quality", result)


if __name__ == "__main__":
    unittest.main()

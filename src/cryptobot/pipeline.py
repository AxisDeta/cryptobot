from __future__ import annotations

from cryptobot.config import BotSettings
from cryptobot.decision.engine import DecisionEngine
from cryptobot.features.market import compute_market_features
from cryptobot.features.sentiment import compute_sentiment_features, merge_event_features
from cryptobot.models.direction import DirectionModel
from cryptobot.models.regime import VolatilityRegimeModel
from cryptobot.schemas import EventSignal, OHLCVBar, OrderBookSnapshot, SentimentPost, SignalSnapshot


def build_feature_vector(market: dict[str, float], sent_plus: dict[str, float]) -> list[float]:
    interaction = {
        "sentiment_x_volume": sent_plus["sentiment_index"] * market["volume_zscore"],
        "sentiment_x_volatility": sent_plus["sentiment_index"] * market["rolling_volatility"],
    }

    return [
        market["log_return_1"],
        market["rolling_volatility"],
        market["volume_zscore"],
        market["momentum_3"],
        market["order_book_imbalance"],
        market["momentum_10"],
        market["ema_ratio"],
        market["rsi_centered"],
        market["atr_percent"],
        market["range_percent"],
        market["channel_position"],
        market["drawdown_20"],
        sent_plus["sentiment_index"],
        sent_plus["sentiment_momentum"],
        sent_plus["sentiment_volatility"],
        sent_plus["event_bullish_ratio"],
        sent_plus["event_hack_ratio"],
        interaction["sentiment_x_volume"],
        interaction["sentiment_x_volatility"],
    ]


class HybridTradingBot:
    """End-to-end orchestrator: features -> models -> risk-adjusted position."""

    def __init__(self, settings: BotSettings) -> None:
        self.settings = settings
        self.direction_model = DirectionModel()
        self.regime_model = VolatilityRegimeModel()
        self.decision_engine = DecisionEngine(settings)

    def train(
        self,
        feature_rows: list[list[float]],
        direction_targets: list[int],
        realized_vols: list[float],
    ) -> None:
        self.direction_model.fit(feature_rows, direction_targets)
        self.regime_model.fit(realized_vols)

    def infer_snapshot(
        self,
        bars: list[OHLCVBar],
        posts: list[SentimentPost],
        order_book: OrderBookSnapshot | None = None,
        events: list[EventSignal] | None = None,
    ) -> SignalSnapshot:
        market = compute_market_features(bars, order_book)
        sentiment = compute_sentiment_features(posts)
        sent_plus = merge_event_features(sentiment, events)

        vector = build_feature_vector(market, sent_plus)

        p_up = self.direction_model.predict_proba(vector)
        expected_vol = market["rolling_volatility"]
        high_vol_prob = self.regime_model.predict_high_vol_probability(expected_vol)
        confidence = max(p_up, 1.0 - p_up) * (1.0 - high_vol_prob)

        return SignalSnapshot(
            direction_prob_up=p_up,
            expected_volatility=expected_vol,
            sentiment_index=sent_plus["sentiment_index"],
            confidence=confidence,
        )

    def recommend_position(
        self,
        bars: list[OHLCVBar],
        posts: list[SentimentPost],
        order_book: OrderBookSnapshot | None = None,
        events: list[EventSignal] | None = None,
    ) -> float:
        snapshot = self.infer_snapshot(bars, posts, order_book, events)
        return self.decision_engine.decide(snapshot)

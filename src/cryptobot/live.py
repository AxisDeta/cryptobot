from __future__ import annotations

from cryptobot.features.market import compute_market_features
from cryptobot.features.sentiment import compute_sentiment_features, merge_event_features
from cryptobot.pipeline import build_feature_vector
from cryptobot.schemas import EventSignal, OHLCVBar, SentimentPost


def select_high_impact_posts(posts: list[SentimentPost], min_engagement: int) -> list[SentimentPost]:
    return [p for p in posts if p.upvotes >= min_engagement or p.comments >= min_engagement]


def build_training_set(
    bars: list[OHLCVBar],
    posts: list[SentimentPost],
    events: list[EventSignal] | None = None,
    min_history: int = 30,
) -> tuple[list[list[float]], list[int], list[float]]:
    if len(bars) < max(4, min_history + 2):
        raise ValueError("not enough bars to build training set")

    rows: list[list[float]] = []
    targets: list[int] = []
    realized_vols: list[float] = []

    for i in range(min_history, len(bars) - 1):
        history = bars[: i + 1]
        market = compute_market_features(history)
        posts_t = [p for p in posts if p.ts <= bars[i].ts]
        sent = compute_sentiment_features(posts_t)
        ev_t = [e for e in (events or [])]
        sent_plus = merge_event_features(sent, ev_t)
        rows.append(build_feature_vector(market, sent_plus))
        targets.append(1 if bars[i + 1].close > bars[i].close else 0)
        realized_vols.append(market["rolling_volatility"])

    return rows, targets, realized_vols

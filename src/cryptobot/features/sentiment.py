from __future__ import annotations

from statistics import mean, pstdev

from cryptobot.data.sentiment import engagement_weight
from cryptobot.schemas import EventSignal, SentimentPost

LEXICON = {
    "bullish": 1.0,
    "moon": 1.0,
    "buy": 0.5,
    "adoption": 0.6,
    "bearish": -1.0,
    "sell": -0.5,
    "hack": -0.8,
    "dump": -0.9,
}


def _score_text(text: str) -> float:
    t = text.lower()
    score = 0.0
    hits = 0
    for key, val in LEXICON.items():
        if key in t:
            score += val
            hits += 1
    if hits == 0:
        return 0.0
    return max(-1.0, min(1.0, score / hits))


def compute_sentiment_features(posts: list[SentimentPost], window: int = 30) -> dict[str, float]:
    if not posts:
        return {
            "sentiment_index": 0.0,
            "sentiment_momentum": 0.0,
            "sentiment_volatility": 0.0,
        }

    weighted: list[float] = []
    for p in posts:
        score = _score_text(f"{p.title} {p.body}")
        weighted.append(score * engagement_weight(p))

    sent_index = mean(weighted)
    win = weighted[-window:] if len(weighted) >= window else weighted
    sent_vol = pstdev(win) if len(win) > 1 else 0.0
    prev = mean(weighted[:-5]) if len(weighted) > 5 else 0.0
    momentum = sent_index - prev

    return {
        "sentiment_index": sent_index,
        "sentiment_momentum": momentum,
        "sentiment_volatility": sent_vol,
    }


def merge_event_features(features: dict[str, float], events: list[EventSignal] | None) -> dict[str, float]:
    out = dict(features)
    if not events:
        out["event_bullish_ratio"] = 0.0
        out["event_hack_ratio"] = 0.0
        return out

    bullish = sum(1 for e in events if e.sentiment.lower() == "bullish")
    hack = sum(1 for e in events if e.event.lower() == "hack")
    n = float(len(events))
    out["event_bullish_ratio"] = bullish / n
    out["event_hack_ratio"] = hack / n
    return out

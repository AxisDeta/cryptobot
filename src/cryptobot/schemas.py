from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class OHLCVBar:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(slots=True)
class OrderBookSnapshot:
    ts: datetime
    bid_volume: float
    ask_volume: float


@dataclass(slots=True)
class SentimentPost:
    ts: datetime
    source: str
    title: str
    body: str
    upvotes: int
    comments: int


@dataclass(slots=True)
class EventSignal:
    sentiment: str
    asset: str
    event: str
    horizon: str


@dataclass(slots=True)
class SignalSnapshot:
    direction_prob_up: float
    expected_volatility: float
    sentiment_index: float
    confidence: float

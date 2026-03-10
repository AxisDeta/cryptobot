from __future__ import annotations

from cryptobot.config import BotSettings
from cryptobot.schemas import SignalSnapshot


def position_size(target_vol: float, predicted_vol: float, max_leverage: float = 2.0) -> float:
    if predicted_vol <= 0:
        return 0.0
    raw = target_vol / predicted_vol
    return max(-max_leverage, min(max_leverage, raw))


def allow_trade(snapshot: SignalSnapshot, settings: BotSettings) -> bool:
    return (
        snapshot.confidence >= settings.confidence_threshold
        and snapshot.expected_volatility <= settings.max_allowed_volatility
    )

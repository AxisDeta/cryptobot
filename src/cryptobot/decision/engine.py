from __future__ import annotations

from cryptobot.config import BotSettings
from cryptobot.decision.risk import allow_trade, position_size
from cryptobot.schemas import SignalSnapshot


class DecisionEngine:
    def __init__(self, settings: BotSettings) -> None:
        self.settings = settings

    def decide(self, snapshot: SignalSnapshot) -> float:
        if not allow_trade(snapshot, self.settings):
            return 0.0

        direction = 1.0 if snapshot.direction_prob_up >= 0.5 else -1.0
        scaled = position_size(self.settings.target_volatility, snapshot.expected_volatility)
        return direction * abs(scaled)

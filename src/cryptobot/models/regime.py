from __future__ import annotations

from statistics import quantiles


class VolatilityRegimeModel:
    """Regime classifier using fitted realized-volatility thresholds."""

    def __init__(self) -> None:
        self.q1 = 0.0
        self.q2 = 0.0

    def fit(self, realized_vols: list[float]) -> None:
        if len(realized_vols) < 4:
            raise ValueError("need at least 4 volatility observations")
        q = quantiles(realized_vols, n=3, method="inclusive")
        self.q1, self.q2 = q[0], q[1]

    def predict_regime(self, vol: float) -> int:
        if vol < self.q1:
            return 0
        if vol < self.q2:
            return 1
        return 2

    def predict_high_vol_probability(self, vol: float) -> float:
        if self.q2 <= 0:
            return 0.0
        if vol >= self.q2:
            return 0.9
        if vol >= self.q1:
            return 0.4
        return 0.1

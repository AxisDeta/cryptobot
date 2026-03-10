from __future__ import annotations

import math
from statistics import mean, pstdev

from cryptobot.schemas import OHLCVBar, OrderBookSnapshot


def _safe_div(a: float, b: float) -> float:
    return a / b if b else 0.0


def _ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    alpha = 2.0 / (period + 1.0)
    out = values[0]
    for v in values[1:]:
        out = (alpha * v) + ((1.0 - alpha) * out)
    return out


def _rsi(closes: list[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    gains: list[float] = []
    losses: list[float] = []
    for i in range(-period, 0):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_gain = mean(gains) if gains else 0.0
    avg_loss = mean(losses) if losses else 0.0
    if avg_loss <= 1e-12:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _atr_percent(bars: list[OHLCVBar], period: int = 14) -> float:
    if len(bars) < period + 1:
        return 0.0
    trs: list[float] = []
    for i in range(-period, 0):
        h = bars[i].high
        l = bars[i].low
        pc = bars[i - 1].close
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
    atr = mean(trs) if trs else 0.0
    close = bars[-1].close
    return _safe_div(atr, close)


def compute_market_features(
    bars: list[OHLCVBar],
    order_book: OrderBookSnapshot | None = None,
    vol_window: int = 20,
) -> dict[str, float]:
    if len(bars) < 4:
        raise ValueError("need at least 4 bars")

    closes = [b.close for b in bars]
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]
    volumes = [b.volume for b in bars]

    returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes)) if closes[i - 1] > 0]
    win = returns[-vol_window:] if len(returns) >= vol_window else returns
    rolling_vol = pstdev(win) if len(win) > 1 else 0.0

    v_mean = mean(volumes[:-1]) if len(volumes) > 1 else volumes[-1]
    v_std = pstdev(volumes[:-1]) if len(volumes) > 2 else 0.0
    volume_z = (volumes[-1] - v_mean) / v_std if v_std else 0.0

    m3_ref = closes[-3] if len(closes) >= 3 else closes[0]
    m10_ref = closes[-10] if len(closes) >= 10 else closes[0]
    momentum_3 = _safe_div(closes[-1] - m3_ref, m3_ref)
    momentum_10 = _safe_div(closes[-1] - m10_ref, m10_ref)

    ema12 = _ema(closes[-60:], 12)
    ema26 = _ema(closes[-60:], 26)
    ema_ratio = _safe_div(ema12 - ema26, closes[-1])

    rsi14 = _rsi(closes, period=14)
    rsi_centered = (rsi14 - 50.0) / 50.0

    atrp = _atr_percent(bars, period=14)
    range_pct = _safe_div(highs[-1] - lows[-1], closes[-1])

    highs20 = highs[-20:]
    lows20 = lows[-20:]
    ch_high = max(highs20)
    ch_low = min(lows20)
    channel_pos = _safe_div(closes[-1] - ch_low, ch_high - ch_low) * 2.0 - 1.0 if ch_high > ch_low else 0.0

    recent = closes[-20:]
    peak = max(recent)
    drawdown = _safe_div(closes[-1] - peak, peak)

    ob_imbalance = 0.0
    if order_book is not None:
        ob_imbalance = _safe_div(
            order_book.bid_volume - order_book.ask_volume,
            order_book.bid_volume + order_book.ask_volume,
        )

    return {
        "log_return_1": returns[-1] if returns else 0.0,
        "rolling_volatility": rolling_vol,
        "volume_zscore": volume_z,
        "momentum_3": momentum_3,
        "order_book_imbalance": ob_imbalance,
        "momentum_10": momentum_10,
        "ema_ratio": ema_ratio,
        "rsi_centered": rsi_centered,
        "atr_percent": atrp,
        "range_percent": range_pct,
        "channel_position": channel_pos,
        "drawdown_20": drawdown,
    }



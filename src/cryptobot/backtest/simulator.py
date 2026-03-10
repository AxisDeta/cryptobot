from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class BacktestResult:
    equity_curve: list[float]
    returns: list[float]
    sharpe: float
    max_drawdown: float
    profit_factor: float


def _max_drawdown(equity: list[float]) -> float:
    peak = equity[0]
    mdd = 0.0
    for x in equity:
        peak = max(peak, x)
        dd = (peak - x) / peak if peak else 0.0
        mdd = max(mdd, dd)
    return mdd


def _sharpe(returns: list[float]) -> float:
    if len(returns) < 2:
        return 0.0
    avg = sum(returns) / len(returns)
    var = sum((r - avg) ** 2 for r in returns) / (len(returns) - 1)
    std = var ** 0.5
    return (avg / std) * (len(returns) ** 0.5) if std else 0.0


def _profit_factor(returns: list[float]) -> float:
    gains = sum(r for r in returns if r > 0)
    losses = -sum(r for r in returns if r < 0)
    return gains / losses if losses else 0.0


def run_backtest(
    market_returns: list[float],
    positions: list[float],
    fee_bps: float,
    slippage_bps: float,
    start_equity: float = 1.0,
) -> BacktestResult:
    if len(market_returns) != len(positions):
        raise ValueError("market_returns and positions must have same length")

    cost = (fee_bps + slippage_bps) / 10000.0
    equity = [start_equity]
    strat_returns: list[float] = []
    prev_pos = 0.0

    for r, pos in zip(market_returns, positions):
        turnover = abs(pos - prev_pos)
        gross = pos * r
        net = gross - turnover * cost
        strat_returns.append(net)
        equity.append(equity[-1] * (1.0 + net))
        prev_pos = pos

    return BacktestResult(
        equity_curve=equity,
        returns=strat_returns,
        sharpe=_sharpe(strat_returns),
        max_drawdown=_max_drawdown(equity),
        profit_factor=_profit_factor(strat_returns),
    )

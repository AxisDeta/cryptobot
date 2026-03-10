from __future__ import annotations

from cryptobot.backtest.simulator import BacktestResult, run_backtest


def walk_forward_backtest(
    returns: list[float],
    positions: list[float],
    split_index: int,
    fee_bps: float,
    slippage_bps: float,
) -> tuple[BacktestResult, BacktestResult]:
    if split_index <= 0 or split_index >= len(returns):
        raise ValueError("split_index must split the sample")

    train = run_backtest(returns[:split_index], positions[:split_index], fee_bps, slippage_bps)
    test = run_backtest(returns[split_index:], positions[split_index:], fee_bps, slippage_bps)
    return train, test

import unittest

from cryptobot.backtest.simulator import run_backtest
from cryptobot.backtest.walkforward import walk_forward_backtest


class BacktestTests(unittest.TestCase):
    def test_backtest_metrics(self) -> None:
        returns = [0.01, -0.02, 0.015, 0.005, -0.01]
        positions = [1.0, 1.0, -0.5, 0.5, 0.0]
        res = run_backtest(returns, positions, fee_bps=10, slippage_bps=5)
        self.assertEqual(len(res.returns), len(returns))
        self.assertGreaterEqual(res.max_drawdown, 0.0)

    def test_walk_forward(self) -> None:
        returns = [0.01, -0.01, 0.02, -0.005, 0.01, 0.03]
        positions = [1, 0.5, -1, 0.2, 1, 0]
        train, test = walk_forward_backtest(returns, positions, split_index=3, fee_bps=10, slippage_bps=5)
        self.assertEqual(len(train.returns), 3)
        self.assertEqual(len(test.returns), 3)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import argparse
import json

from cryptobot.config import BotSettings
from cryptobot.service import LivePredictionRequest, generate_live_prediction


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run live hybrid crypto trading signal.")
    parser.add_argument("--exchange", default="binance")
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--timeframe", default=None)
    parser.add_argument("--ohlcv-limit", type=int, default=240)
    parser.add_argument("--reddit-limit", type=int, default=60)
    parser.add_argument("--subreddits", default="cryptocurrency,bitcoin,ethtrader")
    parser.add_argument("--min-engagement", type=int, default=100)
    parser.add_argument("--llm-model", default="gemini-2.5-flash")
    parser.add_argument("--disable-llm", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    settings = BotSettings.from_env()
    req = LivePredictionRequest(
        exchange=args.exchange,
        symbol=args.symbol,
        timeframe=args.timeframe,
        ohlcv_limit=args.ohlcv_limit,
        reddit_limit=args.reddit_limit,
        subreddits=tuple(s.strip() for s in args.subreddits.split(",") if s.strip()),
        min_engagement=args.min_engagement,
        llm_model=args.llm_model,
        disable_llm=bool(args.disable_llm),
    )
    result = generate_live_prediction(settings, req)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


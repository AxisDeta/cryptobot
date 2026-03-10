from __future__ import annotations

from datetime import datetime
from typing import Sequence

from cryptobot.schemas import OHLCVBar, OrderBookSnapshot


class CCXTMarketDataClient:
    """Thin ccxt wrapper with lazy import so tests do not require ccxt."""

    def __init__(self, exchange_id: str = "binance") -> None:
        self.exchange_id = exchange_id

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 300) -> list[OHLCVBar]:
        try:
            import ccxt  # type: ignore
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("ccxt is required for live market data") from exc

        exchange = getattr(ccxt, self.exchange_id)()
        rows: Sequence[Sequence[float]] = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        bars: list[OHLCVBar] = []
        for ts_ms, o, h, l, c, v in rows:
            bars.append(
                OHLCVBar(
                    ts=datetime.utcfromtimestamp(ts_ms / 1000.0),
                    open=float(o),
                    high=float(h),
                    low=float(l),
                    close=float(c),
                    volume=float(v),
                )
            )
        return bars

    def fetch_order_book_imbalance(self, symbol: str, depth: int = 20) -> OrderBookSnapshot:
        try:
            import ccxt  # type: ignore
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("ccxt is required for live market data") from exc

        exchange = getattr(ccxt, self.exchange_id)()
        ob = exchange.fetch_order_book(symbol, limit=depth)
        bid_volume = sum(level[1] for level in ob.get("bids", []))
        ask_volume = sum(level[1] for level in ob.get("asks", []))
        ts_ms = ob.get("timestamp") or 0
        return OrderBookSnapshot(
            ts=datetime.utcfromtimestamp(ts_ms / 1000.0) if ts_ms else datetime.utcnow(),
            bid_volume=float(bid_volume),
            ask_volume=float(ask_volume),
        )


class ForexMarketDataClient:
    """Forex OHLCV via yfinance. Order book is unavailable for spot FX."""

    _interval_map = {
        "1m": "1m",
        "2m": "2m",
        "5m": "5m",
        "15m": "15m",
        "30m": "30m",
        "60m": "60m",
        "90m": "90m",
        "1h": "60m",
        "4h": "60m",
        "1d": "1d",
        "1w": "1wk",
    }

    _ordered_intraday = [
        ("1m", 1),
        ("2m", 2),
        ("5m", 5),
        ("15m", 15),
        ("30m", 30),
        ("60m", 60),
        ("90m", 90),
    ]

    def _to_yf_symbol(self, symbol: str) -> str:
        s = symbol.strip().upper().replace("-", "/")
        if "/" in s:
            base, quote = s.split("/", 1)
            return f"{base}{quote}=X"
        if s.endswith("=X"):
            return s
        return f"{s}=X"

    def _to_yf_interval(self, timeframe: str) -> str:
        import re

        tf = timeframe.strip().lower()
        if tf in self._interval_map:
            return self._interval_map[tf]

        m = re.fullmatch(r"\s*(\d+)\s*([mhdw])\s*", tf)
        if not m:
            return "60m"
        qty = int(m.group(1))
        unit = m.group(2)

        if unit == "m":
            closest = min(self._ordered_intraday, key=lambda p: abs(p[1] - qty))
            return closest[0]
        if unit == "h":
            mins = qty * 60
            closest = min(self._ordered_intraday, key=lambda p: abs(p[1] - mins))
            return closest[0]
        if unit == "d":
            return "1d"
        if unit == "w":
            return "1wk"
        return "60m"

    def _period_for_interval(self, interval: str, limit: int) -> str:
        if interval.endswith("m"):
            if limit <= 500:
                return "60d"
            return "730d"
        if interval.endswith("d"):
            return "10y"
        if interval.endswith("wk"):
            return "10y"
        return "2y"

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 300) -> list[OHLCVBar]:
        try:
            import numpy as np  # type: ignore
            import pandas as pd  # type: ignore
            import yfinance as yf  # type: ignore
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("yfinance is required for forex live data") from exc

        yf_symbol = self._to_yf_symbol(symbol)
        primary_interval = self._to_yf_interval(timeframe)

        intervals = [primary_interval]
        if primary_interval != "60m":
            intervals.append("60m")
        if "1d" not in intervals:
            intervals.append("1d")
        if "1wk" not in intervals:
            intervals.append("1wk")

        df = None
        for interval in intervals:
            period = self._period_for_interval(interval, limit)
            try:
                df = yf.download(
                    tickers=yf_symbol,
                    period=period,
                    interval=interval,
                    auto_adjust=False,
                    progress=False,
                    threads=False,
                )
            except Exception:
                df = None
            if df is not None and not df.empty:
                break

        if df is None or df.empty:
            return []

        if hasattr(df, "columns") and isinstance(df.columns, pd.MultiIndex):
            flat_cols = []
            for col in df.columns:
                if isinstance(col, tuple):
                    flat_cols.append("_".join([str(x) for x in col if x not in (None, "")]))
                else:
                    flat_cols.append(str(col))
            df.columns = flat_cols

        def _pick_col(target: str) -> str | None:
            target_l = target.lower()
            exact = [c for c in df.columns if str(c).lower() == target_l]
            if exact:
                return exact[0]
            starts = [c for c in df.columns if str(c).lower().startswith(target_l)]
            return starts[0] if starts else None

        col_open = _pick_col("open")
        col_high = _pick_col("high")
        col_low = _pick_col("low")
        col_close = _pick_col("close")
        col_volume = _pick_col("volume")

        def _to_float(v) -> float:
            if isinstance(v, pd.Series):
                v = v.iloc[0] if not v.empty else 0.0
            elif isinstance(v, np.ndarray):
                if v.size == 0:
                    v = 0.0
                else:
                    v = v.flat[0]
            elif isinstance(v, (list, tuple)):
                v = v[0] if len(v) else 0.0

            if v is None:
                return 0.0
            try:
                if pd.isna(v):
                    return 0.0
            except Exception:
                pass
            try:
                return float(v)
            except Exception:
                return 0.0

        rows = df.tail(limit)
        bars: list[OHLCVBar] = []
        for idx, row in rows.iterrows():
            ts = idx.to_pydatetime() if hasattr(idx, "to_pydatetime") else datetime.utcnow()
            bars.append(
                OHLCVBar(
                    ts=ts,
                    open=_to_float(row[col_open] if col_open else 0.0),
                    high=_to_float(row[col_high] if col_high else 0.0),
                    low=_to_float(row[col_low] if col_low else 0.0),
                    close=_to_float(row[col_close] if col_close else 0.0),
                    volume=_to_float(row[col_volume] if col_volume else 0.0),
                )
            )
        return bars

    def fetch_order_book_imbalance(self, symbol: str, depth: int = 20) -> OrderBookSnapshot:
        return OrderBookSnapshot(ts=datetime.utcnow(), bid_volume=0.0, ask_volume=0.0)

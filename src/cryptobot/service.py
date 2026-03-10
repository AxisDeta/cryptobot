from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import json
import re
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from cryptobot.backtest.simulator import run_backtest
from cryptobot.config import BotSettings
from cryptobot.data.market import CCXTMarketDataClient, ForexMarketDataClient
from cryptobot.data.sentiment import RedditSentimentClient
from cryptobot.features.market import compute_market_features
from cryptobot.features.sentiment import compute_sentiment_features, merge_event_features
from cryptobot.nlp.events import _extract_json_object
from cryptobot.nlp.gemini_client import GeminiJSONClient
from cryptobot.pipeline import HybridTradingBot, build_feature_vector
from cryptobot.storage.mysql_store import MySQLStore

MIN_TIMEFRAME_MINUTES = 1
MAX_TIMEFRAME_MINUTES = 10080  # 1 week
MODEL_CACHE_TTL_SECONDS = 300
SUPPORTED_FOREX_PAIRS = {
    "EUR/USD",
    "GBP/USD",
    "USD/JPY",
    "USD/CHF",
    "AUD/USD",
    "USD/CAD",
    "NZD/USD",
    "EUR/GBP",
    "EUR/JPY",
    "GBP/JPY",
}


@dataclass(slots=True)
class LivePredictionRequest:
    market_type: str = "crypto"
    exchange: str = "binance"
    symbol: str | None = None
    timeframe: str | None = None
    ohlcv_limit: int = 300
    reddit_limit: int = 120
    subreddits: tuple[str, ...] = ("cryptocurrency", "bitcoin", "ethtrader", "CryptoMarkets")
    min_engagement: int = 5
    llm_model: str = "gemini-2.0-flash"
    disable_llm: bool = False


@dataclass(slots=True)
class AdhocBacktestRequest:
    market_type: str = "crypto"
    exchange: str = "binance"
    symbol: str | None = None
    timeframe: str | None = None
    horizon_bars: int = 96
    threshold: float = 0.55
@dataclass(slots=True)
class _CachedModel:
    bot: HybridTradingBot
    bars_signature: tuple[int, int, float]
    trained_at: datetime
    model_quality: dict[str, float]


_MODEL_CACHE: dict[tuple[str, str, str, str], _CachedModel] = {}
_MODEL_CACHE_LOCK = threading.Lock()


def _timeframe_to_minutes(tf: str) -> int:
    m = re.fullmatch(r"\s*(\d+)\s*([mhdw])\s*", tf.lower())
    if not m:
        raise ValueError("Invalid timeframe format. Use forms like 1m, 15m, 1h, 4h, 1d, 1w.")
    qty = int(m.group(1))
    unit = m.group(2)
    mult = {"m": 1, "h": 60, "d": 1440, "w": 10080}[unit]
    return qty * mult


def _validate_timeframe(tf: str) -> str:
    mins = _timeframe_to_minutes(tf)
    if mins < MIN_TIMEFRAME_MINUTES or mins > MAX_TIMEFRAME_MINUTES:
        raise ValueError(f"Timeframe out of range. Minimum is 1m and maximum is 1w (10080m). You entered: {tf}")
    return tf.strip().lower()


def _normalize_symbol(market_type: str, symbol: str) -> str:
    s = symbol.strip().upper().replace("-", "/")
    if market_type == "forex":
        if len(s) == 6 and "/" not in s:
            s = f"{s[:3]}/{s[3:]}"
        if s not in SUPPORTED_FOREX_PAIRS:
            allowed = ", ".join(sorted(SUPPORTED_FOREX_PAIRS))
            raise ValueError(f"Unsupported forex pair '{symbol}'. Supported pairs: {allowed}")
    return s


def load_reddit_posts(settings: BotSettings, subreddits: list[str], limit: int):
    if not settings.reddit_client_id or not settings.reddit_client_secret:
        return []

    client = RedditSentimentClient(
        client_id=settings.reddit_client_id,
        client_secret=settings.reddit_client_secret,
        user_agent=settings.reddit_user_agent,
        username=settings.reddit_username,
        password=settings.reddit_password,
    )

    posts = []
    for sub in subreddits:
        posts.extend(client.fetch_new_posts(subreddit=sub, limit=limit))
    return posts


def _persist_run_if_configured(
    settings: BotSettings,
    request: LivePredictionRequest,
    result: dict[str, Any],
    posts,
    events,
) -> int | None:
    if not settings.mysql_enabled:
        return None
    store = MySQLStore(settings)
    store.ensure_schema()
    return store.save_run(asdict(request), result, posts, events)


def _ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    alpha = 2.0 / (period + 1.0)
    out = [values[0]]
    for v in values[1:]:
        out.append((alpha * v) + ((1.0 - alpha) * out[-1]))
    return out


def _forecast_grid(timeframe: str) -> tuple[int, int]:
    horizon_minutes = max(1, _timeframe_to_minutes(timeframe))
    if horizon_minutes <= 12:
        steps = horizon_minutes
    elif horizon_minutes <= 120:
        steps = 12
    elif horizon_minutes <= 1440:
        steps = 24
    else:
        steps = 30
    step_minutes = max(1, horizon_minutes // max(1, steps))
    steps = max(1, min(120, horizon_minutes // step_minutes))
    return step_minutes, steps


def _build_chart_payload(
    bars,
    trained_bot: HybridTradingBot,
    posts,
    events,
    order_book,
    market_type: str,
    timeframe: str,
    direction_prob_up: float,
    expected_volatility: float,
    min_history: int = 30,
) -> dict[str, Any]:
    del trained_bot, posts, events, order_book, market_type, min_history

    last_close = float(bars[-1].close)
    vol = max(1e-6, float(expected_volatility))
    p_up = max(0.0, min(1.0, float(direction_prob_up)))

    step_minutes, steps = _forecast_grid(timeframe)
    step_ms = step_minutes * 60 * 1000
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    drift = (p_up - 0.5) * 2.0 * vol * 0.35
    candles: list[dict[str, float | int]] = []
    probs: list[dict[str, float | int]] = []

    prev_close = max(1e-9, last_close)
    for i in range(1, steps + 1):
        t = now_ms + (i * step_ms)
        p_step = max(0.0, min(1.0, 0.5 + ((p_up - 0.5) * (1.0 - (0.02 * (i - 1))))))
        local_drift = (p_step - 0.5) * 2.0 * vol * 0.35
        close_p = max(1e-9, prev_close * (1.0 + local_drift))

        spread = max(1e-5, vol * (0.6 + (0.02 * i)))
        high_p = max(prev_close, close_p) * (1.0 + spread)
        low_p = max(1e-9, min(prev_close, close_p) * (1.0 - spread))

        candles.append(
            {
                "time": int(t),
                "open": float(prev_close),
                "high": float(high_p),
                "low": float(low_p),
                "close": float(close_p),
            }
        )
        probs.append({"time": int(t), "value": float(p_step)})
        prev_close = close_p

    close_series = [float(c["close"]) for c in candles]
    ema_fast_series = _ema(close_series, 12)
    ema_slow_series = _ema(close_series, 26)
    ema_fast = [{"time": candles[i]["time"], "value": ema_fast_series[i]} for i in range(len(candles))]
    ema_slow = [{"time": candles[i]["time"], "value": ema_slow_series[i]} for i in range(len(candles))]

    markers: list[dict[str, float | int | str]] = []
    prob_by_time = {int(p["time"]): float(p["value"]) for p in probs}
    for i in range(1, len(candles)):
        prev_diff = ema_fast_series[i - 1] - ema_slow_series[i - 1]
        curr_diff = ema_fast_series[i] - ema_slow_series[i]
        t = int(candles[i]["time"])
        p_curr = prob_by_time.get(t, 0.5)
        if prev_diff <= 0.0 < curr_diff and p_curr >= 0.56:
            markers.append({"time": t, "price": float(candles[i]["low"]), "side": "buy"})
        if prev_diff >= 0.0 > curr_diff and p_curr <= 0.44:
            markers.append({"time": t, "price": float(candles[i]["high"]), "side": "sell"})

    context_count = max(1, min(len(bars), (24 * 60) // max(1, step_minutes)))
    context_bars = bars[-context_count:]
    context_candles = [
        {
            "time": int(bar.ts.timestamp() * 1000),
            "open": float(bar.open),
            "high": float(bar.high),
            "low": float(bar.low),
            "close": float(bar.close),
        }
        for bar in context_bars
    ]

    return {
        "chart_mode": "history",
        "candles": candles,
        "context_candles": context_candles,
        "direction_probs": probs,
        "ema_fast": ema_fast,
        "ema_slow": ema_slow,
        "trade_markers": markers,
    }

def _signal_label(direction_prob_up: float, confidence: float) -> str:
    if confidence < 0.5:
        return "Wait"
    if direction_prob_up >= 0.57:
        return "Bullish"
    if direction_prob_up <= 0.43:
        return "Bearish"
    return "Neutral"


def _build_metric_notes(result: dict[str, Any]) -> dict[str, str]:
    p_up = float(result["direction_prob_up"])
    confidence = float(result["confidence"])
    pos = float(result["recommended_position"])

    direction_text = "Probability of next-bar upside. >55% is bullish bias, <45% is bearish bias."
    confidence_text = "Signal quality score after risk adjustment. Prefer entries above 55%."
    vol_text = "Expected short-term volatility. Higher values mean wider stop-loss ranges may be needed."
    position_text = "Position size from -1 to +1. Positive=long, negative=short, 0=no-trade."

    if confidence < 0.55:
        guidance = "No trade: confidence is below 55%, so edge quality is weak."
        action = "WAIT"
    elif p_up >= 0.57 and pos > 0:
        guidance = "Potential long setup: bullish probability and confidence are aligned."
        action = "BUY BIAS"
    elif p_up <= 0.43 and pos < 0:
        guidance = "Potential short setup: bearish probability and confidence are aligned."
        action = "SELL BIAS"
    else:
        guidance = "Mixed signal: wait for stronger directional alignment before entering."
        action = "WAIT"

    return {
        "direction_prob_up": direction_text,
        "confidence": confidence_text,
        "expected_volatility": vol_text,
        "recommended_position": position_text,
        "trade_action": action,
        "trade_guidance": guidance,
    }


def _fallback_ai_explanation(result: dict[str, Any]) -> str:
    return (
        f"{result.get('trade_action', 'WAIT')}: {result.get('trade_guidance', 'No clear edge yet.')}"
        f" Up probability is {float(result.get('direction_prob_up', 0.0)) * 100:.1f}%"
        f" with confidence {float(result.get('confidence', 0.0)) * 100:.1f}%."
    )


def _build_ai_explanation(settings: BotSettings, request: LivePredictionRequest, result: dict[str, Any]) -> tuple[str, str]:
    if request.disable_llm:
        return _fallback_ai_explanation(result), "disabled_by_request"
    if not settings.gemini_api_key:
        return _fallback_ai_explanation(result), "missing_gemini_key"

    prompt = (
        "You are a trading assistant for retail traders. "
        "Return ONLY valid JSON with keys: explanation, action. "
        "Action must be one of BUY, SELL, WAIT. "
        "Explanation must be 2 short sentences in plain language with risk caution.\n"
        f"Market: {result.get('market_type')}\n"
        f"Symbol: {result.get('symbol')}\n"
        f"Timeframe: {result.get('timeframe')}\n"
        f"Signal: {result.get('signal')}\n"
        f"Direction probability up: {result.get('direction_prob_up')}\n"
        f"Confidence: {result.get('confidence')}\n"
        f"Expected volatility: {result.get('expected_volatility')}\n"
        f"Recommended position: {result.get('recommended_position')}\n"
        f"Rule guidance: {result.get('trade_action')} - {result.get('trade_guidance')}\n"
    )

    try:
        llm = GeminiJSONClient(api_key=settings.gemini_api_key, model=request.llm_model)
        with ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(llm.complete_json, prompt)
            raw = fut.result(timeout=3.0)
        payload = json.loads(_extract_json_object(raw))
        explanation = str(payload.get("explanation") or "").strip()
        action = str(payload.get("action") or "").strip().upper()
        if not explanation:
            return _fallback_ai_explanation(result), "invalid_response"
        if action and action in {"BUY", "SELL", "WAIT"}:
            return f"{action}: {explanation}", "ok"
        return explanation, "ok"
    except FuturesTimeoutError:
        return _fallback_ai_explanation(result), "timeout"
    except Exception:
        return _fallback_ai_explanation(result), "error"


def _fetch_crypto(settings: BotSettings, request: LivePredictionRequest, symbol: str, timeframe: str):
    def _fetch_bars_task():
        client = CCXTMarketDataClient(request.exchange)
        bars = client.fetch_ohlcv(symbol=symbol, timeframe=timeframe, limit=request.ohlcv_limit)
        used_tf = timeframe
        used_fallback = False
        if not bars:
            used_tf = "1h"
            bars = client.fetch_ohlcv(symbol=symbol, timeframe=used_tf, limit=request.ohlcv_limit)
            used_fallback = True
        if not bars:
            raise RuntimeError(f"No candles returned for {symbol} on timeframe {timeframe}.")
        return bars, used_tf, used_fallback

    def _fetch_orderbook_task():
        client = CCXTMarketDataClient(request.exchange)
        return client.fetch_order_book_imbalance(symbol=symbol, depth=20)

    with ThreadPoolExecutor(max_workers=3) as pool:
        bars_f = pool.submit(_fetch_bars_task)
        orderbook_f = pool.submit(_fetch_orderbook_task)
        reddit_f = pool.submit(load_reddit_posts, settings, list(request.subreddits), request.reddit_limit)

        bars, used_timeframe, used_fallback_timeframe = bars_f.result()
        try:
            order_book = orderbook_f.result(timeout=2.0)
        except Exception:
            order_book = None

    reddit_status = "ok"
    try:
        posts = reddit_f.result(timeout=4.0)
        if not settings.reddit_client_id or not settings.reddit_client_secret:
            reddit_status = "missing_reddit_credentials"
        elif not posts:
            reddit_status = "no_recent_posts"
    except Exception:
        posts = []
        reddit_status = "reddit_fetch_error"

    return bars, order_book, posts, reddit_status, used_timeframe, used_fallback_timeframe


def _fetch_forex(request: LivePredictionRequest, symbol: str, timeframe: str):
    client = ForexMarketDataClient()
    used_symbol = symbol
    bars = client.fetch_ohlcv(symbol=used_symbol, timeframe=timeframe, limit=request.ohlcv_limit)
    used_tf = timeframe
    used_fallback = False

    if not bars:
        used_tf = "1h"
        bars = client.fetch_ohlcv(symbol=used_symbol, timeframe=used_tf, limit=request.ohlcv_limit)
        used_fallback = True

    if not bars and used_symbol != "EUR/USD":
        used_symbol = "EUR/USD"
        used_tf = "1h"
        bars = client.fetch_ohlcv(symbol=used_symbol, timeframe=used_tf, limit=request.ohlcv_limit)
        used_fallback = True

    if not bars:
        raise RuntimeError("Unable to load forex candles currently. Please retry shortly.")

    order_book = client.fetch_order_book_imbalance(symbol=used_symbol, depth=0)
    posts: list[Any] = []
    return bars, order_book, posts, "disabled_for_forex", used_tf, used_fallback, used_symbol

def _bars_signature(bars) -> tuple[int, int, float]:
    last = bars[-1]
    return (int(last.ts.timestamp()), len(bars), round(float(last.close), 8))


def _compute_training_rows(bars, posts, events, order_book, min_history: int = 30):
    X: list[list[float]] = []
    y: list[int] = []
    realized_vols: list[float] = []
    posts_sorted = sorted(posts, key=lambda p: p.ts) if posts else []
    seen_posts = []
    post_idx = 0

    for i in range(min_history, len(bars) - 1):
        history = bars[: i + 1]
        market = compute_market_features(history, order_book)
        while post_idx < len(posts_sorted) and posts_sorted[post_idx].ts <= bars[i].ts:
            seen_posts.append(posts_sorted[post_idx])
            post_idx += 1
        sent = compute_sentiment_features(seen_posts)
        sent_plus = merge_event_features(sent, events)
        X.append(build_feature_vector(market, sent_plus))
        y.append(1 if bars[i + 1].close > bars[i].close else 0)
        realized_vols.append(float(market["rolling_volatility"]))
    return X, y, realized_vols


def _evaluate_walkforward(bot: HybridTradingBot, X: list[list[float]], y: list[int]) -> dict[str, float]:
    n = len(X)
    if n < 40:
        return {"wf_accuracy": 0.0, "wf_brier": 0.0, "wf_trade_rate": 0.0, "wf_avg_edge": 0.0}

    split = max(30, int(n * 0.7))
    split = min(split, n - 10)
    Xv = X[split:]
    yv = y[split:]
    if not Xv:
        return {"wf_accuracy": 0.0, "wf_brier": 0.0, "wf_trade_rate": 0.0, "wf_avg_edge": 0.0}

    probs = [float(bot.direction_model.predict_proba(row)) for row in Xv]
    preds = [1 if p >= 0.5 else 0 for p in probs]
    accuracy = sum(1 for t, p in zip(yv, preds) if t == p) / float(len(yv))
    brier = sum((p - float(t)) ** 2 for t, p in zip(yv, probs)) / float(len(yv))

    trades = []
    for t, p in zip(yv, probs):
        if p >= 0.55:
            trades.append(1.0 if t == 1 else -1.0)
        elif p <= 0.45:
            trades.append(1.0 if t == 0 else -1.0)
    trade_rate = len(trades) / float(len(yv))
    avg_edge = (sum(trades) / float(len(trades))) if trades else 0.0

    return {
        "wf_accuracy": round(accuracy, 6),
        "wf_brier": round(brier, 6),
        "wf_trade_rate": round(trade_rate, 6),
        "wf_avg_edge": round(avg_edge, 6),
    }


def _get_or_train_bot(
    settings: BotSettings,
    request: LivePredictionRequest,
    market_type: str,
    symbol: str,
    timeframe: str,
    bars,
    posts,
    events,
    order_book,
) -> tuple[HybridTradingBot, dict[str, float], bool]:
    key = (market_type, request.exchange.lower(), symbol.upper(), timeframe)
    sig = _bars_signature(bars)
    now = datetime.now(timezone.utc)

    with _MODEL_CACHE_LOCK:
        cached = _MODEL_CACHE.get(key)
        if cached:
            age = (now - cached.trained_at).total_seconds()
            if cached.bars_signature == sig and age <= MODEL_CACHE_TTL_SECONDS:
                quality = dict(cached.model_quality)
                quality["cache_hit"] = 1.0
                quality["cache_age_sec"] = round(age, 3)
                return cached.bot, quality, True

    X, y, realized_vols = _compute_training_rows(bars, posts, events, order_book)
    if len(X) < 20:
        raise RuntimeError("Not enough data to train model for this market/timeframe.")

    bot = HybridTradingBot(settings)
    bot.train(X, y, realized_vols)

    quality = dict(getattr(bot.direction_model, "metrics", {}))
    quality.update(_evaluate_walkforward(bot, X, y))
    quality["cache_hit"] = 0.0

    with _MODEL_CACHE_LOCK:
        _MODEL_CACHE[key] = _CachedModel(bot=bot, bars_signature=sig, trained_at=now, model_quality=quality)

    return bot, quality, False


def generate_live_prediction(settings: BotSettings, request: LivePredictionRequest) -> dict[str, Any]:
    market_type = (request.market_type or "crypto").strip().lower()
    if market_type not in {"crypto", "forex"}:
        raise ValueError("Unsupported market_type. Use 'crypto' or 'forex'.")

    default_symbol = settings.symbol if market_type == "crypto" else "EUR/USD"
    symbol = _normalize_symbol(market_type, request.symbol or default_symbol)
    timeframe = _validate_timeframe(request.timeframe or settings.timeframe)

    if market_type == "crypto":
        bars, order_book, posts, reddit_status, used_timeframe, used_fallback_timeframe = _fetch_crypto(settings, request, symbol, timeframe)
    else:
        bars, order_book, posts, reddit_status, used_timeframe, used_fallback_timeframe, used_symbol = _fetch_forex(request, symbol, timeframe)
        symbol = used_symbol

    events: list[Any] = []

    bot, model_quality, _cache_hit = _get_or_train_bot(
        settings=settings,
        request=request,
        market_type=market_type,
        symbol=symbol,
        timeframe=timeframe,
        bars=bars,
        posts=posts,
        events=events,
        order_book=order_book,
    )

    snapshot = bot.infer_snapshot(bars, posts, order_book=order_book, events=events)
    position = bot.decision_engine.decide(snapshot)

    chart_payload = _build_chart_payload(
        bars,
        bot,
        posts=posts,
        events=events,
        order_book=order_book,
        market_type=market_type,
        timeframe=timeframe,
        direction_prob_up=float(snapshot.direction_prob_up),
        expected_volatility=float(snapshot.expected_volatility),
    )

    result: dict[str, Any] = {
        "market_type": market_type,
        "symbol": symbol,
        "timeframe": timeframe,
        "used_timeframe": used_timeframe,
        "used_fallback_timeframe": used_fallback_timeframe,
        "signal": _signal_label(snapshot.direction_prob_up, snapshot.confidence),
        "direction_prob_up": round(snapshot.direction_prob_up, 6),
        "expected_volatility": round(snapshot.expected_volatility, 6),
        "sentiment_index": round(snapshot.sentiment_index, 6),
        "confidence": round(snapshot.confidence, 6),
        "recommended_position": round(position, 6),
        "num_posts": len(posts),
        "num_events": len(events),
        "reddit_status": reddit_status,
        "chart": chart_payload,
        "model_quality": model_quality,
    }
    result["metric_notes"] = _build_metric_notes(result)
    result["trade_guidance"] = result["metric_notes"]["trade_guidance"]
    result["trade_action"] = result["metric_notes"]["trade_action"]
    result["ai_explanation"], result["ai_explanation_status"] = _build_ai_explanation(settings, request, result)

    run_id = _persist_run_if_configured(settings, request, result, posts, events)
    if run_id is not None:
        result["run_id"] = run_id

    return result


def model_cache_overview() -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    with _MODEL_CACHE_LOCK:
        items = []
        for key, entry in _MODEL_CACHE.items():
            market_type, exchange, symbol, timeframe = key
            age = max(0.0, (now - entry.trained_at).total_seconds())
            items.append(
                {
                    "market_type": market_type,
                    "exchange": exchange,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "trained_at": entry.trained_at.isoformat(),
                    "age_seconds": round(age, 3),
                    "quality": dict(entry.model_quality),
                }
            )
    items.sort(key=lambda x: x["age_seconds"])
    return {"count": len(items), "ttl_seconds": MODEL_CACHE_TTL_SECONDS, "items": items}



def run_ad_hoc_backtest(settings: BotSettings, request: AdhocBacktestRequest) -> dict[str, Any]:
    market_type = (request.market_type or "crypto").strip().lower()
    if market_type not in {"crypto", "forex"}:
        raise ValueError("Unsupported market_type. Use 'crypto' or 'forex'.")

    threshold = float(request.threshold)
    if threshold < 0.5 or threshold > 0.8:
        raise ValueError("threshold must be between 0.50 and 0.80")

    horizon = int(request.horizon_bars)
    if horizon < 20 or horizon > 500:
        raise ValueError("horizon_bars must be between 20 and 500")

    default_symbol = settings.symbol if market_type == "crypto" else "EUR/USD"
    symbol = _normalize_symbol(market_type, request.symbol or default_symbol)
    timeframe = _validate_timeframe(request.timeframe or settings.timeframe)

    live_req = LivePredictionRequest(
        market_type=market_type,
        exchange=request.exchange,
        symbol=symbol,
        timeframe=timeframe,
        ohlcv_limit=max(220, horizon + 80),
        reddit_limit=25,
        min_engagement=40,
        llm_model="gemini-2.0-flash",
    )

    if market_type == "crypto":
        bars, order_book, posts, _reddit_status, used_timeframe, used_fallback_timeframe = _fetch_crypto(
            settings, live_req, symbol, timeframe
        )
    else:
        bars, order_book, posts, _reddit_status, used_timeframe, used_fallback_timeframe, used_symbol = _fetch_forex(
            live_req, symbol, timeframe
        )
        symbol = used_symbol

    events: list[Any] = []
    X, y, realized_vols = _compute_training_rows(bars, posts, events, order_book)
    if len(X) < 60:
        raise RuntimeError("Not enough historical samples to run ad-hoc backtest.")

    split = max(40, int(len(X) * 0.7))
    split = min(split, len(X) - 10)

    bot = HybridTradingBot(settings)
    bot.train(X[:split], y[:split], realized_vols[:split])

    eval_rows = X[split:]
    eval_y = y[split:]

    eval_returns: list[float] = []
    min_history = 30
    for i in range(min_history + split, min_history + len(X)):
        prev_close = float(bars[i].close)
        next_close = float(bars[i + 1].close)
        eval_returns.append(((next_close - prev_close) / prev_close) if prev_close else 0.0)

    probs = [float(bot.direction_model.predict_proba(row)) for row in eval_rows]
    positions: list[float] = []
    for p in probs:
        if p >= threshold:
            positions.append(1.0)
        elif p <= (1.0 - threshold):
            positions.append(-1.0)
        else:
            positions.append(0.0)

    if not eval_returns:
        raise RuntimeError("Unable to build backtest returns for selected market/timeframe.")

    m = min(len(eval_returns), len(positions), len(eval_y), horizon)
    eval_returns = eval_returns[:m]
    positions = positions[:m]
    eval_y = eval_y[:m]
    probs = probs[:m]

    res = run_backtest(eval_returns, positions, fee_bps=settings.fee_bps, slippage_bps=settings.slippage_bps)

    wins = 0
    trades = 0
    for t, p in zip(eval_y, probs):
        if p >= threshold:
            trades += 1
            if t == 1:
                wins += 1
        elif p <= (1.0 - threshold):
            trades += 1
            if t == 0:
                wins += 1
    win_rate = (wins / trades) if trades else 0.0

    return {
        "market_type": market_type,
        "exchange": request.exchange,
        "symbol": symbol,
        "timeframe": timeframe,
        "used_timeframe": used_timeframe,
        "used_fallback_timeframe": used_fallback_timeframe,
        "threshold": threshold,
        "horizon_bars": horizon,
        "sample_count": m,
        "trade_count": trades,
        "trade_rate": round((trades / m) if m else 0.0, 6),
        "win_rate": round(win_rate, 6),
        "total_return": round((res.equity_curve[-1] - 1.0) if res.equity_curve else 0.0, 6),
        "sharpe": round(float(res.sharpe), 6),
        "max_drawdown": round(float(res.max_drawdown), 6),
        "profit_factor": round(float(res.profit_factor), 6),
        "model_quality": dict(getattr(bot.direction_model, "metrics", {})),
        "equity_curve": [
            round(float(x), 6)
            for x in (res.equity_curve[-300:] if len(res.equity_curve) > 300 else res.equity_curve)
        ],
    }







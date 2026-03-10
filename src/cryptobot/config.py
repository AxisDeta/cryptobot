from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: str = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass(slots=True)
class BotSettings:
    symbol: str = "BTC/USDT"
    timeframe: str = "1h"
    target_volatility: float = 0.02
    max_allowed_volatility: float = 0.08
    confidence_threshold: float = 0.55
    fee_bps: float = 10.0
    slippage_bps: float = 5.0

    reddit_client_id: str | None = None
    reddit_client_secret: str | None = None
    reddit_username: str | None = None
    reddit_password: str | None = None
    reddit_user_agent: str = "crypto-bot"

    gemini_api_key: str | None = None

    mysql_host: str | None = None
    mysql_port: int = 3306
    mysql_database: str | None = None
    mysql_user: str | None = None
    mysql_password: str | None = None

    app_host: str = "127.0.0.1"
    app_port: int = 8000
    app_base_url: str = "http://127.0.0.1:8000"
    app_session_secret: str = "change-me"

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None

    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str | None = None

    paystack_secret_key: str | None = None
    paystack_public_key: str | None = None
    paystack_webhook_secret: str | None = None
    paystack_callback_url: str | None = None
    paystack_currency: str = "KES"

    pesapal_consumer_key: str | None = None
    pesapal_consumer_secret: str | None = None
    pesapal_callback_url: str | None = None
    pesapal_ipn_url: str | None = None
    pesapal_currency: str = "KES"
    pesapal_api_url: str = "https://pay.pesapal.com/v3"

    admin_emails: str = ""

    @property
    def mysql_enabled(self) -> bool:
        return all([self.mysql_host, self.mysql_database, self.mysql_user, self.mysql_password])

    @classmethod
    def from_env(cls, dotenv_path: str = ".env") -> "BotSettings":
        _load_dotenv(dotenv_path)
        return cls(
            symbol=os.getenv("BOT_SYMBOL", "BTC/USDT"),
            timeframe=os.getenv("BOT_TIMEFRAME", "1h"),
            target_volatility=float(os.getenv("BOT_TARGET_VOL", "0.02")),
            max_allowed_volatility=float(os.getenv("BOT_MAX_VOL", "0.08")),
            confidence_threshold=float(os.getenv("BOT_CONFIDENCE", "0.55")),
            fee_bps=float(os.getenv("BOT_FEE_BPS", "10")),
            slippage_bps=float(os.getenv("BOT_SLIPPAGE_BPS", "5")),
            reddit_client_id=os.getenv("REDDIT_CLIENT_ID"),
            reddit_client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
            reddit_username=os.getenv("REDDIT_USERNAME"),
            reddit_password=os.getenv("REDDIT_PASSWORD"),
            reddit_user_agent=os.getenv("REDDIT_USER_AGENT", "crypto-bot"),
            gemini_api_key=os.getenv("GEMINI_API_KEY"),
            mysql_host=os.getenv("MYSQL_HOST"),
            mysql_port=int(os.getenv("MYSQL_PORT", "3306")),
            mysql_database=os.getenv("MYSQL_DATABASE"),
            mysql_user=os.getenv("MYSQL_USER"),
            mysql_password=os.getenv("MYSQL_PASSWORD"),
            app_host=os.getenv("APP_HOST", "127.0.0.1"),
            app_port=int(os.getenv("APP_PORT", "8000")),
            app_base_url=os.getenv("APP_BASE_URL", "http://127.0.0.1:8000"),
            app_session_secret=os.getenv("APP_SESSION_SECRET", "change-me"),
            smtp_host=os.getenv("SMTP_HOST"),
            smtp_port=int(os.getenv("SMTP_PORT", "587")),
            smtp_user=os.getenv("SMTP_USER"),
            smtp_password=os.getenv("SMTP_PASSWORD"),
            smtp_from_email=os.getenv("SMTP_FROM_EMAIL"),
            google_client_id=os.getenv("GOOGLE_CLIENT_ID"),
            google_client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
            google_redirect_uri=os.getenv("GOOGLE_REDIRECT_URI"),
            paystack_secret_key=os.getenv("PAYSTACK_SECRET_KEY"),
            paystack_public_key=os.getenv("PAYSTACK_PUBLIC_KEY"),
            paystack_webhook_secret=os.getenv("PAYSTACK_WEBHOOK_SECRET"),
            paystack_callback_url=os.getenv("PAYSTACK_CALLBACK_URL"),
            paystack_currency=os.getenv("PAYSTACK_CURRENCY", "KES"),
            pesapal_consumer_key=os.getenv("PESAPAL_CONSUMER_KEY"),
            pesapal_consumer_secret=os.getenv("PESAPAL_CONSUMER_SECRET"),
            pesapal_callback_url=os.getenv("PESAPAL_CALLBACK_URL"),
            pesapal_ipn_url=os.getenv("PESAPAL_IPN_URL"),
            pesapal_currency=os.getenv("PESAPAL_CURRENCY", "KES"),
            pesapal_api_url=os.getenv("PESAPAL_API_URL", "https://pay.pesapal.com/v3").strip(),
            admin_emails=os.getenv("ADMIN_EMAILS", ""),
        )

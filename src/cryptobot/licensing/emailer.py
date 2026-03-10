from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from cryptobot.config import BotSettings

logger = logging.getLogger(__name__)


def send_email(settings: BotSettings, to_email: str, subject: str, body: str) -> bool:
    if not settings.smtp_host or not settings.smtp_user or not settings.smtp_password:
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from_email or settings.smtp_user
    msg["To"] = to_email
    msg.set_content(body)

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
            smtp.starttls()
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
        return True
    except Exception:
        logger.exception("SMTP send failed for subject: %s", subject)
        return False


def send_verification_email(settings: BotSettings, to_email: str, token: str) -> bool:
    base = (settings.app_base_url or "http://127.0.0.1:8000").rstrip("/")
    url = f"{base}/auth/verify-email?token={token}"
    body = (
        "Welcome to CryptoBot.\n\n"
        "Verify your email to continue:\n"
        f"{url}\n\n"
        "This link expires in 30 minutes."
    )
    return send_email(settings, to_email, "CryptoBot Email Verification", body)


def send_activation_key_email(settings: BotSettings, to_email: str, activation_key: str, plan_name: str) -> bool:
    body = (
        "Your CryptoBot payment is confirmed.\n\n"
        f"Plan: {plan_name}\n"
        f"Activation Key: {activation_key}\n\n"
        "Important:\n"
        "- Activate within 14 days\n"
        "- Key binds to one device on first activation\n"
        "- Subscription countdown starts at activation\n"
    )
    return send_email(settings, to_email, "CryptoBot Activation Key", body)


def send_password_reset_email(settings: BotSettings, to_email: str, token: str) -> bool:
    base = (settings.app_base_url or "http://127.0.0.1:8000").rstrip("/")
    url = f"{base}/login?reset_token={token}"
    body = (
        "CryptoBot password reset request.\n\n"
        "Use this link to reset your password:\n"
        f"{url}\n\n"
        "This link expires in 30 minutes. If you did not request this, ignore this email."
    )
    return send_email(settings, to_email, "CryptoBot Password Reset", body)

from __future__ import annotations

import hashlib
import hmac
from typing import Any

import requests

from cryptobot.config import BotSettings


class PaystackClient:
    _session = requests.Session()
    base_url = "https://api.paystack.co"

    def __init__(self, settings: BotSettings) -> None:
        self.settings = settings

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.paystack_secret_key}",
            "Content-Type": "application/json",
        }

    def initialize(
        self,
        *,
        email: str,
        amount_cents: int,
        reference: str,
        callback_url: str,
        currency: str,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        payload: dict[str, Any] = {
            "email": email,
            "amount": int(amount_cents),
            "reference": reference,
            "callback_url": callback_url,
            "currency": currency,
        }
        if metadata:
            payload["metadata"] = metadata

        try:
            resp = self._session.post(
                f"{self.base_url}/transaction/initialize",
                headers=self._headers(),
                json=payload,
                timeout=20,
            )
            return int(resp.status_code), resp.json() if resp.content else {}
        except Exception as exc:
            return 599, {"message": str(exc)}

    def verify(self, reference: str) -> tuple[int, dict[str, Any]]:
        try:
            resp = self._session.get(
                f"{self.base_url}/transaction/verify/{reference}",
                headers=self._headers(),
                timeout=20,
            )
            return int(resp.status_code), resp.json() if resp.content else {}
        except Exception as exc:
            return 599, {"message": str(exc)}

    def friendly_error(self, body: dict[str, Any] | None, fallback: str = "Checkout initialization failed.") -> str:
        if not isinstance(body, dict):
            return fallback
        message = str(body.get("message") or "").strip()
        code = str(body.get("code") or "").strip().lower()
        if code == "unsupported_currency":
            return (
                f"Currency '{self.settings.paystack_currency}' is not enabled on this Paystack account. "
                "Set PAYSTACK_CURRENCY in .env to a supported currency for your account and retry."
            )
        return message or fallback

    def is_valid_signature(self, raw_body: bytes, signature: str | None) -> bool:
        secret = self.settings.paystack_webhook_secret or self.settings.paystack_secret_key or ""
        if not secret:
            return False
        expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha512).hexdigest()
        return hmac.compare_digest(expected, signature or "")


class PesapalClient:
    _session = requests.Session()
    def __init__(self, settings: BotSettings) -> None:
        self.settings = settings
        self.base_url = (settings.pesapal_api_url or "https://pay.pesapal.com/v3").rstrip("/")

    @staticmethod
    def _body(resp: requests.Response) -> dict[str, Any]:
        if not resp.content:
            return {}
        try:
            data = resp.json()
            return data if isinstance(data, dict) else {"data": data}
        except Exception:
            return {"message": resp.text}

    def get_token(self) -> tuple[str | None, dict[str, Any] | None]:
        payload = {
            "consumer_key": self.settings.pesapal_consumer_key,
            "consumer_secret": self.settings.pesapal_consumer_secret,
        }
        try:
            resp = self._session.post(
                f"{self.base_url}/api/Auth/RequestToken",
                json=payload,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                timeout=30,
            )
            body = self._body(resp)
        except Exception as exc:
            return None, {"message": str(exc)}

        token = body.get("token") if isinstance(body, dict) else None
        if resp.status_code >= 300 or not token:
            return None, body
        return str(token), None

    def register_ipn(self, token: str, ipn_url: str) -> tuple[str | None, dict[str, Any] | None]:
        payload = {
            "url": ipn_url,
            "ipn_notification_type": "GET",
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        }
        try:
            resp = self._session.post(f"{self.base_url}/api/URLSetup/RegisterIPN", json=payload, headers=headers, timeout=30)
            body = self._body(resp)
        except Exception as exc:
            return None, {"message": str(exc)}

        ipn_id = body.get("ipn_id") if isinstance(body, dict) else None
        if resp.status_code >= 300 or not ipn_id:
            return None, body
        return str(ipn_id), None

    def submit_order(
        self,
        token: str,
        ipn_id: str,
        reference: str,
        email: str,
        amount: float,
        callback_url: str,
        currency: str,
    ) -> tuple[int, dict[str, Any]]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        }
        payload = {
            "id": reference,
            "currency": currency,
            "amount": float(amount),
            "description": "CryptoBot subscription",
            "callback_url": callback_url,
            "notification_id": ipn_id,
            "billing_address": {
                "email_address": email,
                "phone_number": "254700000000",
                "first_name": "CryptoBot",
                "last_name": "User",
            },
        }
        try:
            resp = self._session.post(f"{self.base_url}/api/Transactions/SubmitOrderRequest", json=payload, headers=headers, timeout=30)
            return int(resp.status_code), self._body(resp)
        except Exception as exc:
            return 599, {"message": str(exc)}

    def get_transaction_status(self, token: str, order_tracking_id: str) -> tuple[int, dict[str, Any]]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        }
        try:
            resp = self._session.get(
                f"{self.base_url}/api/Transactions/GetTransactionStatus",
                params={"orderTrackingId": order_tracking_id},
                headers=headers,
                timeout=30,
            )
            return int(resp.status_code), self._body(resp)
        except Exception as exc:
            return 599, {"message": str(exc)}



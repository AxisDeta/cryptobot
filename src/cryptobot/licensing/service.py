from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from datetime import timedelta
from typing import Any

from cryptobot.config import BotSettings
from cryptobot.licensing.emailer import send_activation_key_email, send_password_reset_email, send_verification_email
from cryptobot.licensing.security import (
    PLANS,
    activation_deadline,
    hash_password,
    hash_value,
    key_hint,
    license_expiry_from,
    new_activation_key,
    new_token,
    utcnow,
    verify_password,
)
from cryptobot.licensing.store import LicensingStore


@dataclass(slots=True)
class CheckoutInitResult:
    payment_reference: str
    provider: str
    redirect_url: str


class LicensingService:
    def __init__(self, settings: BotSettings) -> None:
        self.settings = settings
        self.store = LicensingStore(settings)
        self.store.ensure_schema()

    def _is_admin_email(self, email: str) -> bool:
        raw = self.settings.admin_emails or ""
        admin_set = {x.strip().lower() for x in raw.split(",") if x.strip()}
        return email.strip().lower() in admin_set

    def _user_has_any_license(self, user_id: int) -> bool:
        if not hasattr(self.store, "list_user_licenses"):
            return False
        try:
            rows = self.store.list_user_licenses(user_id=int(user_id), limit=1)
        except Exception:
            return False
        return bool(rows)

    def ensure_signup_trial(self, user_id: int, email: str) -> str | None:
        if self._user_has_any_license(user_id):
            return None
        try:
            return self._grant_signup_trial(user_id=user_id, email=email)
        except Exception:
            return None

    def signup_email(self, email: str, password: str) -> dict[str, Any]:
        email = (email or "").strip().lower()
        if not email or "@" not in email:
            raise ValueError("Valid email is required")
        if len(password or "") < 8:
            raise ValueError("Password must be at least 8 characters")

        existing = self.store.get_user_by_email(email)
        if existing:
            raise ValueError("Email already exists")

        user_id = self.store.create_user(
            email=email,
            password_hash=hash_password(password),
            verified=False,
            is_admin=self._is_admin_email(email),
        )
        token = new_token(24)
        self.store.create_email_verification(user_id=user_id, token_hash=hash_value(token), expires_at=utcnow() + timedelta(minutes=30))
        sent = send_verification_email(self.settings, email, token)
        trial_activation_key = self.ensure_signup_trial(user_id=user_id, email=email)
        return {
            "user_id": user_id,
            "verification_email_sent": bool(sent),
            "trial_activation_key": trial_activation_key,
            "trial_duration_days": 1 if trial_activation_key else 0,
        }

    def _grant_signup_trial(self, user_id: int, email: str) -> str:
        activation_key = new_activation_key()
        trial_reference = f"trial_{uuid.uuid4().hex[:24]}"
        payment_id = self.store.create_payment(
            user_id=int(user_id),
            provider="trial",
            reference=trial_reference,
            plan_code="trial_1d",
            currency="USD",
            amount_cents=0,
            status="completed",
        )
        license_id = self.store.create_license(
            user_id=int(user_id),
            payment_id=int(payment_id),
            plan_code="trial_1d",
            duration_days=1,
            activation_key_hash=hash_value(activation_key),
            activation_key_hint=key_hint(activation_key),
            activation_key_value=activation_key,
            status="issued",
            issued_at=utcnow(),
            activation_deadline_at=activation_deadline(),
        )
        now = utcnow()
        self.store.activate_license(
            int(license_id),
            device_id="account_trial",
            activated_at=now,
            expires_at=now + timedelta(days=1),
        )
        send_activation_key_email(self.settings, email, activation_key, "1-Day Free Trial")
        return activation_key

    def verify_email(self, token: str) -> int | None:
        token_hash = hash_value(token)
        return self.store.verify_email_token(token_hash=token_hash, now=utcnow())

    def request_password_reset(self, email: str) -> dict[str, Any]:
        normalized = (email or "").strip().lower()
        if not normalized or "@" not in normalized:
            return {"email_sent": False}
        user = self.store.get_user_by_email(normalized)
        if not user or not bool(user.get("is_active", 1)):
            return {"email_sent": False}
        token = new_token(24)
        self.store.create_password_reset(
            user_id=int(user["id"]),
            token_hash=hash_value(token),
            expires_at=utcnow() + timedelta(minutes=30),
        )
        sent = send_password_reset_email(self.settings, normalized, token)
        return {"email_sent": bool(sent)}

    def reset_password(self, token: str, new_password: str) -> bool:
        if len(new_password or "") < 8:
            raise ValueError("Password must be at least 8 characters")
        token_hash = hash_value((token or "").strip())
        user_id = self.store.consume_password_reset_token(token_hash=token_hash, now=utcnow())
        if not user_id:
            return False
        self.store.update_user_password(int(user_id), hash_password(new_password))
        return True
    def reset_password_by_email(self, email: str, new_password: str) -> bool:
        normalized = (email or "").strip().lower()
        if not normalized or "@" not in normalized:
            raise ValueError("Valid email is required")
        if len(new_password or "") < 8:
            raise ValueError("Password must be at least 8 characters")
        user = self.store.get_user_by_email(normalized)
        if not user or not bool(user.get("is_active", 1)):
            return False
        self.store.update_user_password(int(user["id"]), hash_password(new_password))
        return True

    def login_email(self, email: str, password: str) -> dict[str, Any] | None:
        normalized = (email or "").strip().lower()
        user = self.store.get_user_by_email(normalized)
        if not user:
            return None
        if not bool(user.get("is_active", 1)):
            return None
        if not user.get("password_hash"):
            return None
        if not verify_password(password, str(user["password_hash"])):
            return None
        self.ensure_signup_trial(user_id=int(user["id"]), email=normalized)
        return user

    def login_google(self, *, email: str, sub: str) -> int:
        normalized = email.strip().lower()
        user_id = self.store.upsert_google_user(email=normalized, google_sub=sub, is_admin=self._is_admin_email(email))
        self.ensure_signup_trial(user_id=int(user_id), email=normalized)
        return user_id

    def create_checkout_record(self, user_id: int, provider: str, plan_code: str, amount_cents: int, currency: str) -> str:
        if plan_code not in PLANS:
            raise ValueError("Unsupported plan")
        reference = f"ctb_{uuid.uuid4().hex[:24]}"
        self.store.create_payment(
            user_id=user_id,
            provider=provider,
            reference=reference,
            plan_code=plan_code,
            currency=currency,
            amount_cents=amount_cents,
            status="pending",
        )
        return reference

    def fulfill_payment(self, reference: str, provider_payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payment = self.store.get_payment_by_reference(reference)
        if not payment:
            raise ValueError("Unknown payment reference")

        if payment.get("status") == "completed":
            return {"already_fulfilled": True}

        plan_code = str(payment["plan_code"])
        plan = PLANS.get(plan_code)
        if not plan:
            raise ValueError("Unknown plan in payment")

        activation_key = new_activation_key()
        self.store.update_payment(int(payment["id"]), status="completed", payload=provider_payload)
        self.store.create_license(
            user_id=int(payment["user_id"]),
            payment_id=int(payment["id"]),
            plan_code=plan_code,
            duration_days=plan.duration_days,
            activation_key_hash=hash_value(activation_key),
            activation_key_hint=key_hint(activation_key),
            activation_key_value=activation_key,
            status="issued",
            issued_at=utcnow(),
            activation_deadline_at=activation_deadline(),
        )

        user = self.store.get_user_by_id(int(payment["user_id"]))
        if user:
            send_activation_key_email(self.settings, str(user["email"]), activation_key, plan.name)

        return {
            "activation_key": activation_key,
            "plan": asdict(plan),
        }

    def activate_key_for_user(self, user_id: int, activation_key: str, device_id: str) -> dict[str, Any]:
        if not activation_key or not device_id:
            raise ValueError("Activation key and device id are required")

        row = self.store.get_license_by_key_hash(hash_value(activation_key.strip()))
        if not row:
            raise ValueError("Invalid activation key")
        if int(row["user_id"]) != int(user_id):
            raise ValueError("Activation key does not belong to this account")

        now = utcnow().replace(tzinfo=None)
        if row["status"] == "issued":
            if row["activation_deadline_at"] < now:
                raise ValueError("Activation key expired before activation")
            # Upgrade/renew logic: preserve remaining active time by extending from latest active expiry.
            latest_expiry = self.store.get_latest_active_expiry_for_user(int(user_id), utcnow())
            start_at = latest_expiry if latest_expiry and latest_expiry > now else now
            expires_at = start_at + timedelta(days=int(row["duration_days"]))
            self.store.activate_license(int(row["id"]), device_id=device_id, activated_at=utcnow(), expires_at=expires_at)
            self.store.supersede_other_active_licenses(int(user_id), keep_license_id=int(row["id"]))
            row = self.store.get_license_by_key_hash(hash_value(activation_key.strip()))

        if row["status"] != "active":
            raise ValueError("License is not active")
        if row.get("expires_at") and row["expires_at"] < now:
            raise ValueError("License expired")

        return {
            "status": "active",
            "expires_at": row.get("expires_at").isoformat() if row.get("expires_at") else None,
            "plan_code": row.get("plan_code"),
        }

    def validate_key_for_user_device(self, user_id: int, activation_key: str, _device_id: str) -> bool:
        try:
            row = self.store.get_license_by_key_hash(hash_value(activation_key.strip()))
            if not row or row.get("status") != "active":
                return False
            if int(row.get("user_id") or 0) != int(user_id):
                return False
            now = utcnow().replace(tzinfo=None)
            if row.get("expires_at") is None or row["expires_at"] <= now:
                return False
            return True
        except Exception:
            return False

    # Admin service wrappers
    def is_admin_user(self, user_id: int) -> bool:
        user = self.store.get_user_by_id(user_id)
        return bool(user and user.get("is_admin"))

    def admin_overview(self) -> dict[str, int]:
        return self.store.overview()

    def admin_list_users(self, limit: int = 200) -> list[dict[str, Any]]:
        return self.store.list_users(limit=limit)

    def admin_set_user_admin(self, user_id: int, is_admin: bool) -> None:
        self.store.set_user_admin(user_id, is_admin)

    def admin_set_user_active(self, user_id: int, is_active: bool) -> None:
        self.store.set_user_active(user_id, is_active)

    def admin_list_payments(self, limit: int = 300) -> list[dict[str, Any]]:
        return self.store.list_payments(limit=limit)

    def admin_list_licenses(self, limit: int = 300) -> list[dict[str, Any]]:
        return self.store.list_licenses(limit=limit)

    def admin_revoke_license(self, license_id: int) -> None:
        self.store.revoke_license(license_id)

    def admin_clear_license_device(self, license_id: int) -> None:
        self.store.clear_license_device(license_id)

    def admin_list_prediction_runs(self, limit: int = 300) -> list[dict[str, Any]]:
        return self.store.list_prediction_runs(limit=limit)
    def get_preferred_activation_key(self, user_id: int) -> str | None:
        try:
            rows = self.store.list_user_licenses(user_id=int(user_id), limit=30)
        except Exception:
            return None
        for row in rows:
            if str(row.get("status") or "").lower() == "active" and row.get("activation_key"):
                return str(row.get("activation_key"))
        for row in rows:
            if str(row.get("status") or "").lower() == "issued" and row.get("activation_key"):
                return str(row.get("activation_key"))
        return None

    def list_user_subscriptions(self, user_id: int, limit: int = 30) -> list[dict[str, Any]]:
        items = self.store.list_user_licenses(user_id=user_id, limit=limit)
        normalized: list[dict[str, Any]] = []
        for row in items:
            item = dict(row)
            for key in ("issued_at", "activated_at", "expires_at"):
                value = item.get(key)
                if hasattr(value, "isoformat"):
                    item[key] = value.isoformat()
            normalized.append(item)
        return normalized





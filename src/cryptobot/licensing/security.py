from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def hash_value(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def new_token(nbytes: int = 24) -> str:
    return secrets.token_urlsafe(nbytes)


def new_activation_key() -> str:
    # Human-shareable but high entropy.
    chunks = [secrets.token_hex(3).upper() for _ in range(4)]
    return "CTB-" + "-".join(chunks)


def key_hint(key: str) -> str:
    if len(key) < 8:
        return "****"
    return f"{key[:6]}...{key[-4:]}"


def hash_password(password: str, salt: str | None = None) -> str:
    if salt is None:
        salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return f"pbkdf2_sha256${salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, salt, digest = stored.split("$", 2)
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    candidate = hash_password(password, salt)
    return secrets.compare_digest(candidate, stored)


@dataclass(frozen=True)
class Plan:
    code: str
    name: str
    duration_days: int
    amount_cents_usd: int


PLANS: dict[str, Plan] = {
    "test_ksh1": Plan(code="test_ksh1", name="Test Access (One-time)", duration_days=1, amount_cents_usd=50000),
    "monthly": Plan(code="monthly", name="Monthly", duration_days=30, amount_cents_usd=150000),
    "quarterly": Plan(code="quarterly", name="Quarterly", duration_days=90, amount_cents_usd=390000),
    "yearly": Plan(code="yearly", name="Yearly", duration_days=365, amount_cents_usd=1200000),
}


def activation_deadline() -> datetime:
    return utcnow() + timedelta(days=14)


def license_expiry_from(days: int) -> datetime:
    return utcnow() + timedelta(days=days)


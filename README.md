# Crypto Trading Bot

Hybrid crypto trading bot with:

- Market microstructure features
- Reddit sentiment + Gemini event extraction
- Direction + volatility regime modeling
- Risk-aware sizing
- Live charted signal UI
- MySQL persistence
- Commercial licensing: signup/login, Google OAuth, Paystack/Pesapal checkout, activation key issuance, device binding, expiry

## Environment

Fill `.env` with:

- Trading/data keys: `REDDIT_*`, `GEMINI_API_KEY`
- Database: `MYSQL_*`
- Licensing/auth: `APP_SESSION_SECRET`, `SMTP_*`, `GOOGLE_*`
- Payments: `PAYSTACK_*`, `PESAPAL_*`

## Install

```bash
python -m pip install -e .
python -m pip install -e .[live]
```

## Run

```bash
python run_web.py
```

Open `http://127.0.0.1:8000`.

## Commercial flow

1. User signs up (email+password) or uses Google login.
2. Email verification required before checkout.
3. User picks plan and provider (Paystack or Pesapal).
4. On successful callback/webhook, system issues activation key and emails it.
5. User activates key on one device.
6. Prediction API requires active, non-expired key bound to that device.

## Key security logic

- Activation key is high entropy and stored hashed in DB.
- Key activation deadline: 14 days after purchase.
- First activation binds to one `device_id`.
- License expiry countdown starts at first activation.
- Same key from another device is rejected.

## Admin Panel

- Set ADMIN_EMAILS in .env (comma-separated).
- Admin users can open /admin to manage users, licenses, payments, and prediction runs.
- Admin actions include: promote/demote admin, activate/deactivate user, revoke license, clear bound device.
